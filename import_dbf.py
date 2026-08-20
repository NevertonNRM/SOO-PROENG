from __future__ import annotations

import struct
from datetime import datetime
from pathlib import Path

from db import connect, init_db, reset_imported_data


ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT.parent / "SOO-PRONEG"


def decode_text(raw: bytes) -> str:
    return raw.decode("latin1", errors="replace").strip()


def parse_value(raw: bytes, field_type: str):
    text = decode_text(raw)
    if field_type == "N":
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    if field_type == "D":
        if len(text) == 8 and text != "00000000":
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        return None
    return text


def read_dbf(path: Path) -> list[dict]:
    data = path.read_bytes()
    if len(data) < 32:
        return []

    record_count = struct.unpack("<I", data[4:8])[0]
    header_len = struct.unpack("<H", data[8:10])[0]
    record_len = struct.unpack("<H", data[10:12])[0]

    fields = []
    offset = 32
    position = 1
    while offset < header_len - 1 and data[offset] != 0x0D:
        name = data[offset : offset + 11].split(b"\x00", 1)[0].decode("latin1").strip()
        field_type = chr(data[offset + 11])
        length = data[offset + 16]
        decimals = data[offset + 17]
        fields.append((name, field_type, length, decimals, position))
        position += length
        offset += 32

    rows = []
    for index in range(record_count):
        base = header_len + index * record_len
        if base + record_len > len(data):
            break
        if data[base] == 0x2A:
            continue
        row = {}
        for name, field_type, length, _decimals, position in fields:
            raw = data[base + position : base + position + length]
            row[name] = parse_value(raw, field_type)
        rows.append(row)
    return rows


def find_dbf(suffix: str) -> Path | None:
    suffix = suffix.upper()
    for path in SOURCE_DIR.glob("*.DBF"):
        name = path.name.upper()
        if " - COPIA" in name:
            continue
        if name == suffix or name.endswith("_" + suffix):
            return path
    return None


def non_empty_code(value: object, blank: str) -> str:
    text = str(value or "").strip()
    return "" if text in {"", blank} else text


def import_parameters(conn, path: Path) -> int:
    rows = read_dbf(path)
    for row in rows:
        conn.execute(
            "INSERT INTO parameters (unit, value) VALUES (?, ?)",
            (row.get("PARUNIDADE") or "", row.get("PARVALOR") or 0),
        )
    return len(rows)


def import_inputs(conn, path: Path) -> int:
    rows = read_dbf(path)
    for row in rows:
        code = non_empty_code(row.get("INSCODIGO"), "0000")
        if not code:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO inputs
            (code, name, access_code, price, unit, price_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                row.get("INSNOME") or "",
                row.get("INSACESSO") or "",
                row.get("INSPRECO") or 0,
                row.get("INSUNIDADE") or "",
                row.get("INSDATA"),
            ),
        )
    return len(rows)


def import_taxes(conn, path: Path) -> int:
    rows = read_dbf(path)
    for row in rows:
        code = non_empty_code(row.get("TAXCODIGO"), "00")
        if not code:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO taxes
            (code, name, access_code, percent)
            VALUES (?, ?, ?, ?)
            """,
            (
                code,
                row.get("TAXNOME") or "",
                row.get("TAXACESSO") or "",
                row.get("TAXPERC") or 0,
            ),
        )
    return len(rows)


def import_descriptions(conn, path: Path) -> int:
    rows = read_dbf(path)
    for row in rows:
        code = non_empty_code(row.get("DESCODIGO"), "000")
        if not code:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO budget_descriptions
            (code, item, name)
            VALUES (?, ?, ?)
            """,
            (code, row.get("DESITEM") or "", row.get("DESNOME") or ""),
        )
    return len(rows)


def import_services(conn, path: Path) -> int:
    rows = read_dbf(path)
    for row in rows:
        code = non_empty_code(row.get("SERCODIGO"), "0000")
        if not code:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO services
            (code, item, name, access_code, unit, legacy_price)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                row.get("SERITEM") or "",
                row.get("SERNOME") or "",
                row.get("SERACESSO") or "",
                row.get("SERUNIDADE") or "",
                row.get("SERPRECO") or 0,
            ),
        )
        conn.execute("DELETE FROM service_inputs WHERE service_code = ?", (code,))
        conn.execute("DELETE FROM service_taxes WHERE service_code = ?", (code,))
        for pos in range(1, 16):
            input_code = non_empty_code(row.get(f"SERINS{pos:02d}"), "0000")
            quantity = row.get(f"SERQTD{pos:02d}") or 0
            if input_code:
                conn.execute(
                    """
                    INSERT INTO service_inputs
                    (service_code, position, input_code, quantity)
                    VALUES (?, ?, ?, ?)
                    """,
                    (code, pos, input_code, quantity),
                )
        for pos in range(1, 6):
            tax_code = non_empty_code(row.get(f"SERTAX{pos:02d}"), "00")
            if tax_code:
                conn.execute(
                    """
                    INSERT INTO service_taxes
                    (service_code, position, tax_code)
                    VALUES (?, ?, ?)
                    """,
                    (code, pos, tax_code),
                )
    return len(rows)


def import_projects(conn, path: Path) -> int:
    rows = read_dbf(path)
    for index, row in enumerate(rows, start=1):
        name = row.get("INFOBRA") or ""
        if not name:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO projects
            (id, client, name, address, city, state, budget_date, responsible,
             schedule_period, max_period, total_value, start_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                index,
                row.get("INFCLIENTE") or "",
                name,
                row.get("INFENDER") or "",
                row.get("INFCIDADE") or "",
                row.get("INFESTADO") or "",
                row.get("INFDATA"),
                row.get("INFRESPONS") or "",
                row.get("INFCROPER") or "",
                int(row.get("INFPERMAX") or 0),
                row.get("INFVALOR") or 0,
                row.get("INFDATAINI"),
            ),
        )
    return len(rows)


def import_system(conn, path: Path) -> int:
    rows = read_dbf(path)
    if not rows:
        return 0
    row = rows[0]
    conn.execute(
        """
        INSERT OR REPLACE INTO system_info
        (id, client, address, city, state, phone, telex, document, selected_project)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.get("SISCLIENTE") or "",
            row.get("SISENDER") or "",
            row.get("SISCIDADE") or "",
            row.get("SISESTADO") or "",
            row.get("SISFONE") or "",
            row.get("SISTELEX") or "",
            row.get("SISCGC") or "",
            int(row.get("SISORC") or 0),
        ),
    )
    return len(rows)


def import_simple_project_table(conn, path: Path, table: str, project_id: int = 20) -> int:
    rows = read_dbf(path)
    if table == "schedule_items":
        for row in rows:
            conn.execute(
                "INSERT INTO schedule_items (project_id, item, name, total, percent) VALUES (?, ?, ?, ?, ?)",
                (project_id, row.get("CROITEM") or "", row.get("CRONOME") or "", row.get("CROTOT") or 0, row.get("CROPERC") or 0),
            )
    elif table == "schedule_periods":
        for row in rows:
            conn.execute(
                "INSERT INTO schedule_periods (project_id, item, period_number, percent) VALUES (?, ?, ?, ?)",
                (project_id, row.get("PERITEM") or "", row.get("PERNUM") or "", row.get("PERPERC") or 0),
            )
    elif table == "labor_dimensions":
        for row in rows:
            conn.execute(
                "INSERT INTO labor_dimensions (project_id, input_code, journey) VALUES (?, ?, ?)",
                (project_id, row.get("DIMCOD") or "", row.get("DIMJOR") or 0),
            )
    elif table == "executed_services":
        for row in rows:
            conn.execute(
                "INSERT INTO executed_services (project_id, service_code, executed_date, quantity) VALUES (?, ?, ?, ?)",
                (project_id, row.get("EXECOD") or "", row.get("EXEDATA"), row.get("EXEQUANT") or 0),
            )
    return len(rows)


IMPORTERS = [
    ("PARAMETR.DBF", import_parameters),
    ("INSUMOS.DBF", import_inputs),
    ("TAXAS.DBF", import_taxes),
    ("DESCRICA.DBF", import_descriptions),
    ("SERVICOS.DBF", import_services),
    ("INFORMA.DBF", import_projects),
    ("SISTEMA.DBF", import_system),
]


def import_all(source_dir: Path = SOURCE_DIR) -> dict:
    global SOURCE_DIR
    SOURCE_DIR = source_dir
    conn = connect()
    init_db(conn)
    reset_imported_data(conn)
    result = {"source": str(source_dir), "files": [], "imported_at": datetime.now().isoformat(timespec="seconds")}
    try:
        for suffix, importer in IMPORTERS:
            path = find_dbf(suffix)
            if not path:
                result["files"].append({"file": suffix, "rows": 0, "status": "missing"})
                continue
            rows = importer(conn, path)
            conn.execute("INSERT INTO import_log (source_file, rows_imported) VALUES (?, ?)", (path.name, rows))
            result["files"].append({"file": path.name, "rows": rows, "status": "ok"})

        extras = [
            ("CRONOG20.DBF", "schedule_items"),
            ("PERIOD20.DBF", "schedule_periods"),
            ("DIMENS20.DBF", "labor_dimensions"),
            ("EXESER20.DBF", "executed_services"),
        ]
        for suffix, table in extras:
            path = find_dbf(suffix)
            if path:
                rows = import_simple_project_table(conn, path, table)
                conn.execute("INSERT INTO import_log (source_file, rows_imported) VALUES (?, ?)", (path.name, rows))
                result["files"].append({"file": path.name, "rows": rows, "status": "ok"})

        conn.execute("INSERT INTO metadata (key, value) VALUES (?, ?)", ("source_dir", str(source_dir)))
        conn.execute("INSERT INTO metadata (key, value) VALUES (?, ?)", ("imported_at", result["imported_at"]))
        conn.commit()
    finally:
        conn.close()
    return result


if __name__ == "__main__":
    info = import_all()
    for item in info["files"]:
        print(f"{item['status']:7} {item['rows']:5} {item['file']}")
