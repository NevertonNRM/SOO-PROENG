from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from db import DB_PATH, connect, init_db
from import_dbf import SOURCE_DIR, import_all


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
HOST = "127.0.0.1"
PORT = 8775
LOG_PATH = ROOT / "server.log"


def log(text: str):
    try:
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(text + "\n")
    except OSError:
        pass


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def ensure_database():
    if not DB_PATH.exists():
        return import_all(SOURCE_DIR)
    conn = connect()
    try:
        init_db(conn)
        count = conn.execute("SELECT COUNT(*) AS total FROM inputs").fetchone()["total"]
    finally:
        conn.close()
    if count == 0:
        return import_all(SOURCE_DIR)
    return None


def get_parameter(conn):
    row = conn.execute("SELECT unit, value FROM parameters WHERE value > 0 ORDER BY id LIMIT 1").fetchone()
    if not row:
        return {"unit": "R$", "value": 1}
    return {"unit": row["unit"] or "R$", "value": row["value"] or 1}


def get_setting(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return default if not row else row["value"]


def set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()


def active_work(conn):
    work_id = get_setting(conn, "active_work_id", "")
    if work_id:
        row = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
        if row:
            return dict(row)
    row = conn.execute("SELECT * FROM works ORDER BY id DESC LIMIT 1").fetchone()
    return None if not row else dict(row)


def recalc_work_item(conn, work_id: int, item_id: int, quantity: float):
    work = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
    if not work:
        raise ValueError("Obra nao encontrada")
    item = conn.execute("SELECT * FROM unified_items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        raise ValueError("Item nao encontrado")
    if item["kind"] == "COMPOSICAO":
        calc = calculate_unified_composition(conn, item_id, work["uf"])
        unit_price = calc["calculated_total"] if calc else 0
    else:
        unit_price = item_price_for_uf(conn, item_id, work["uf"]) or 0
    total_price = unit_price * quantity
    return unit_price, total_price


def tax_matches(tax_access: str, input_access: str) -> bool:
    tax_access = (tax_access or "").ljust(4)[:4]
    input_access = (input_access or "").ljust(4)[:4]
    if tax_access == "****":
        return True
    for idx, char in enumerate(tax_access):
        if char != "*" and input_access[idx] != char:
            return False
    return True


def calculate_service(conn, code: str):
    service = conn.execute("SELECT * FROM services WHERE code = ?", (code,)).fetchone()
    if not service:
        return None

    taxes = rows_to_dicts(
        conn.execute(
            """
            SELECT st.position, t.code, t.name, t.access_code, t.percent
            FROM service_taxes st
            JOIN taxes t ON t.code = st.tax_code
            WHERE st.service_code = ?
            ORDER BY st.position
            """,
            (code,),
        )
    )

    rows = conn.execute(
        """
        SELECT si.position, si.quantity, i.code, i.name, i.access_code, i.price, i.unit
        FROM service_inputs si
        LEFT JOIN inputs i ON i.code = si.input_code
        WHERE si.service_code = ?
        ORDER BY si.position
        """,
        (code,),
    ).fetchall()

    parameter = get_parameter(conn)
    divisor = parameter["value"] or 1
    material_total = 0.0
    labor_total = 0.0
    items = []

    for row in rows:
        input_access = row["access_code"] or ""
        tax_sum = 0.0
        tax_factor = 0.0
        applied = []
        for tax in taxes:
            if tax_matches(tax["access_code"], input_access):
                percent = tax["percent"] or 0
                tax_sum = tax_sum + (tax_sum * percent / 100) + percent
                if tax_factor == 0:
                    tax_factor = percent / 100 + 1
                else:
                    tax_factor = tax_factor * (percent / 100 + 1)
                applied.append({"code": tax["code"], "name": tax["name"], "percent": percent})

        if taxes:
            unit_with_tax = (row["price"] or 0) * tax_factor
        else:
            unit_with_tax = row["price"] or 0
        total = unit_with_tax * (row["quantity"] or 0)
        bucket = "material" if input_access[:1] == "P" else "labor"
        if bucket == "material":
            material_total += total
        else:
            labor_total += total
        items.append(
            {
                "position": row["position"],
                "code": row["code"],
                "name": row["name"] or "(insumo nao encontrado)",
                "access_code": input_access,
                "unit": row["unit"] or "",
                "quantity": row["quantity"] or 0,
                "price": row["price"] or 0,
                "tax_percent": tax_sum,
                "unit_with_tax": unit_with_tax,
                "total": total,
                "bucket": bucket,
                "applied_taxes": applied,
            }
        )

    material_unit = material_total / divisor
    labor_unit = labor_total / divisor
    calculated = round(material_unit + labor_unit, 2)
    legacy = service["legacy_price"] or 0
    return {
        "service": dict(service),
        "parameter": parameter,
        "taxes": taxes,
        "items": items,
        "totals": {
            "material": round(material_unit, 2),
            "labor": round(labor_unit, 2),
            "calculated": calculated,
            "legacy": legacy,
            "difference": round(calculated - legacy, 2),
        },
    }


def summary(conn):
    return {
        "db_path": str(DB_PATH),
        "inputs": conn.execute("SELECT COUNT(*) AS total FROM inputs").fetchone()["total"],
        "services": conn.execute("SELECT COUNT(*) AS total FROM services").fetchone()["total"],
        "taxes": conn.execute("SELECT COUNT(*) AS total FROM taxes").fetchone()["total"],
        "descriptions": conn.execute("SELECT COUNT(*) AS total FROM budget_descriptions").fetchone()["total"],
        "projects": conn.execute("SELECT COUNT(*) AS total FROM projects").fetchone()["total"],
        "sources": conn.execute("SELECT COUNT(*) AS total FROM data_sources").fetchone()["total"],
        "unified_items": conn.execute("SELECT COUNT(*) AS total FROM unified_items").fetchone()["total"],
        "active_uf": get_setting(conn, "active_uf", "SC"),
        "active_work": active_work(conn),
        "metadata": rows_to_dicts(conn.execute("SELECT key, value FROM metadata ORDER BY key")),
    }


def unified_item_detail(conn, item_id: int):
    item = conn.execute(
        """
        SELECT ui.*, ds.name AS source_name, ds.code AS source_code, ds.reference
        FROM unified_items ui
        JOIN data_sources ds ON ds.id = ui.source_id
        WHERE ui.id = ?
        """,
        (item_id,),
    ).fetchone()
    if not item:
        return None
    prices = rows_to_dicts(
        conn.execute(
            "SELECT uf, price, percent_as, reference FROM unified_prices WHERE item_id = ? ORDER BY uf LIMIT 40",
            (item_id,),
        )
    )
    classifications = rows_to_dicts(
        conn.execute(
            """
            SELECT d.name AS dimension, d.code AS dimension_code, o.name AS option_name, o.code AS option_code,
                   ic.source, ic.confidence
            FROM item_classifications ic
            JOIN classification_options o ON o.id = ic.option_id
            JOIN classification_dimensions d ON d.id = o.dimension_id
            WHERE ic.item_id = ?
            ORDER BY d.sort_order, o.sort_order
            """,
            (item_id,),
        )
    )
    components = rows_to_dicts(
        conn.execute(
            """
            SELECT child_kind, child_external_code, description, unit, coefficient, status
            FROM unified_composition_items
            WHERE parent_item_id = ?
            ORDER BY id
            LIMIT 100
            """,
            (item_id,),
        )
    )
    return {"item": dict(item), "prices": prices, "classifications": classifications, "components": components}


def item_price_for_uf(conn, item_id: int, uf: str):
    row = conn.execute(
        """
        SELECT price
        FROM unified_prices
        WHERE item_id = ?
          AND (uf = ? OR uf = '' OR uf IS NULL)
        ORDER BY CASE WHEN uf = ? THEN 0 WHEN uf = '' OR uf IS NULL THEN 1 ELSE 2 END
        LIMIT 1
        """,
        (item_id, uf, uf),
    ).fetchone()
    return None if not row else row["price"]


def calculate_unified_composition(conn, item_id: int, uf: str, depth: int = 0, seen: set[int] | None = None):
    if seen is None:
        seen = set()
    if item_id in seen or depth > 8:
        return {"total": 0, "items": [], "warning": "ciclo ou profundidade maxima"}
    seen.add(item_id)

    item = conn.execute("SELECT id, kind, external_code, description, unit FROM unified_items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return None

    direct_price = item_price_for_uf(conn, item_id, uf)
    if item["kind"] != "COMPOSICAO":
        return {
            "item": dict(item),
            "uf": uf,
            "direct_price": direct_price,
            "calculated_total": direct_price or 0,
            "items": [],
        }

    rows = conn.execute(
        """
        SELECT rci.*, ui.id AS linked_item_id, ui.kind AS linked_kind, ui.external_code AS linked_code,
               ui.description AS linked_description, ui.unit AS linked_unit
        FROM resolved_composition_items rci
        LEFT JOIN unified_items ui ON ui.id = rci.resolved_child_item_id
        WHERE rci.parent_item_id = ?
        ORDER BY rci.id
        """,
        (item_id,),
    ).fetchall()

    total = 0.0
    calculated_items = []
    for row in rows:
        coefficient = row["coefficient"] or 0
        child_id = row["linked_item_id"]
        child_direct_price = item_price_for_uf(conn, child_id, uf) if child_id else None
        child_calculated_price = child_direct_price or 0
        child_breakdown = []
        calculation_basis = "preco_tabela"

        if child_id and row["child_kind"] == "COMPOSICAO":
            nested = calculate_unified_composition(conn, child_id, uf, depth + 1, seen.copy())
            if nested:
                child_calculated_price = nested["calculated_total"]
                child_breakdown = nested["items"]
                calculation_basis = "composicao_calculada"

        line_total = child_calculated_price * coefficient
        total += line_total
        calculated_items.append(
            {
                "kind": row["child_kind"],
                "code": row["resolved_child_code"],
                "original_code": row["original_child_code"],
                "description": row["linked_description"] or row["description"],
                "unit": row["linked_unit"] or row["unit"],
                "coefficient": coefficient,
                "table_price": child_direct_price,
                "calculated_unit_price": child_calculated_price,
                "line_total": line_total,
                "status": row["status"],
                "calculation_basis": calculation_basis,
                "was_substituted": bool(row["was_substituted"]),
                "children": child_breakdown,
            }
        )

    return {
        "item": dict(item),
        "uf": uf,
        "direct_price": direct_price,
        "calculated_total": total,
        "difference": total - (direct_price or 0),
        "items": calculated_items,
    }


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, path: Path, content_type: str):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.send_static(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        if parsed.path == "/static/app.css":
            return self.send_static(STATIC_DIR / "app.css", "text/css; charset=utf-8")
        if parsed.path == "/static/app.js":
            return self.send_static(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")

        conn = connect()
        try:
            qs = parse_qs(parsed.query)
            if parsed.path == "/api/summary":
                return self.send_json(summary(conn))
            if parsed.path == "/api/app-context":
                return self.send_json({"active_uf": get_setting(conn, "active_uf", "SC")})
            if parsed.path == "/api/inputs":
                q = (qs.get("q", [""])[0] or "").strip()
                like = f"%{q}%"
                rows = conn.execute(
                    """
                    SELECT * FROM inputs
                    WHERE ? = '' OR code LIKE ? OR name LIKE ? OR access_code LIKE ?
                    ORDER BY code
                    LIMIT 100
                    """,
                    (q, like, like, like),
                ).fetchall()
                return self.send_json(rows_to_dicts(rows))
            if parsed.path == "/api/taxes":
                rows = conn.execute("SELECT * FROM taxes ORDER BY code").fetchall()
                return self.send_json(rows_to_dicts(rows))
            if parsed.path == "/api/projects":
                rows = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
                return self.send_json(rows_to_dicts(rows))
            if parsed.path == "/api/works":
                rows = rows_to_dicts(conn.execute("SELECT * FROM works ORDER BY id DESC"))
                active = active_work(conn)
                return self.send_json({"works": rows, "active": active})
            if parsed.path == "/api/work-items":
                work_id = int((qs.get("work_id", ["0"])[0] or "0"))
                if work_id == 0:
                    work = active_work(conn)
                    work_id = 0 if not work else work["id"]
                rows = conn.execute(
                    """
                    SELECT wi.*, ui.external_code, ui.description, ui.unit, ui.kind, ds.name AS source_name
                    FROM work_items wi
                    JOIN unified_items ui ON ui.id = wi.item_id
                    JOIN data_sources ds ON ds.id = ui.source_id
                    WHERE wi.work_id = ?
                    ORDER BY wi.id
                    """,
                    (work_id,),
                ).fetchall()
                total = sum(row["total_price"] or 0 for row in rows)
                return self.send_json({"items": rows_to_dicts(rows), "total": total})
            if parsed.path == "/api/sources":
                rows = conn.execute(
                    """
                    SELECT ds.*,
                           COUNT(ui.id) AS items
                    FROM data_sources ds
                    LEFT JOIN unified_items ui ON ui.source_id = ds.id
                    GROUP BY ds.id
                    ORDER BY ds.kind, ds.name
                    """
                ).fetchall()
                return self.send_json(rows_to_dicts(rows))
            if parsed.path == "/api/classifications":
                rows = conn.execute(
                    """
                    SELECT d.code AS dimension_code, d.name AS dimension, d.allow_multiple,
                           o.code AS option_code, o.name AS option_name
                    FROM classification_dimensions d
                    JOIN classification_options o ON o.dimension_id = d.id
                    ORDER BY d.sort_order, o.sort_order
                    """
                ).fetchall()
                return self.send_json(rows_to_dicts(rows))
            if parsed.path == "/api/equivalences":
                status = (qs.get("status", [""])[0] or "").strip()
                q = (qs.get("q", [""])[0] or "").strip()
                like = f"%{q}%"
                rows = conn.execute(
                    """
                    SELECT eq.id, eq.status, eq.legacy_code, eq.sinapi_code, eq.match_score, eq.match_method, eq.notes,
                           legacy.description AS legacy_description, legacy.unit AS legacy_unit,
                           sinapi.description AS sinapi_description, sinapi.unit AS sinapi_unit
                    FROM input_equivalences eq
                    JOIN unified_items legacy ON legacy.id = eq.legacy_item_id
                    LEFT JOIN unified_items sinapi ON sinapi.id = eq.sinapi_item_id
                    WHERE (? = '' OR eq.status = ?)
                      AND (? = '' OR legacy.description LIKE ? OR eq.legacy_code LIKE ? OR sinapi.description LIKE ? OR eq.sinapi_code LIKE ?)
                    ORDER BY
                        CASE eq.status WHEN 'approved' THEN 3 WHEN 'suggested' THEN 1 ELSE 2 END,
                        eq.match_score DESC,
                        eq.legacy_code
                    LIMIT 300
                    """,
                    (status, status, q, like, like, like, like),
                ).fetchall()
                summary_rows = conn.execute(
                    "SELECT status, COUNT(*) AS total FROM input_equivalences GROUP BY status ORDER BY status"
                ).fetchall()
                return self.send_json({"rows": rows_to_dicts(rows), "summary": rows_to_dicts(summary_rows)})
            if parsed.path == "/api/unified-items":
                q = (qs.get("q", [""])[0] or "").strip()
                source_id = (qs.get("source_id", [""])[0] or "").strip()
                kind = (qs.get("kind", [""])[0] or "").strip()
                like = f"%{q}%"
                rows = conn.execute(
                    """
                    SELECT ui.id, ui.kind, ui.external_code, ui.description, ui.unit, ui.group_name,
                           ds.name AS source_name, ds.code AS source_code,
                           (SELECT price FROM unified_prices p WHERE p.item_id = ui.id ORDER BY CASE WHEN p.uf = 'SC' THEN 0 WHEN p.uf = '' THEN 1 ELSE 2 END, p.uf LIMIT 1) AS price
                    FROM unified_items ui
                    JOIN data_sources ds ON ds.id = ui.source_id
                    WHERE (? = '' OR ui.description LIKE ? OR ui.external_code LIKE ? OR ui.group_name LIKE ?)
                      AND (? = '' OR ui.source_id = CAST(? AS INTEGER))
                      AND (? = '' OR ui.kind = ?)
                    ORDER BY ds.name, ui.kind, ui.external_code
                    LIMIT 150
                    """,
                    (q, like, like, like, source_id, source_id, kind, kind),
                ).fetchall()
                return self.send_json(rows_to_dicts(rows))
            if parsed.path == "/api/unified-item":
                item_id = int((qs.get("id", ["0"])[0] or "0"))
                data = unified_item_detail(conn, item_id)
                if not data:
                    return self.send_json({"error": "Item nao encontrado"}, 404)
                return self.send_json(data)
            if parsed.path == "/api/calculate-composition":
                item_id = int((qs.get("id", ["0"])[0] or "0"))
                uf = (qs.get("uf", [get_setting(conn, "active_uf", "SC")])[0] or "SC").strip().upper()
                data = calculate_unified_composition(conn, item_id, uf)
                if not data:
                    return self.send_json({"error": "Composicao nao encontrada"}, 404)
                return self.send_json(data)
            if parsed.path == "/api/services":
                q = (qs.get("q", [""])[0] or "").strip()
                like = f"%{q}%"
                rows = conn.execute(
                    """
                    SELECT code, item, name, access_code, unit, legacy_price
                    FROM services
                    WHERE ? = '' OR code LIKE ? OR item LIKE ? OR name LIKE ? OR access_code LIKE ?
                    ORDER BY code
                    LIMIT 100
                    """,
                    (q, like, like, like, like),
                ).fetchall()
                return self.send_json(rows_to_dicts(rows))
            if parsed.path == "/api/service":
                code = (qs.get("code", [""])[0] or "").strip()
                data = calculate_service(conn, code)
                if not data:
                    return self.send_json({"error": "Servico nao encontrado"}, 404)
                return self.send_json(data)
        finally:
            conn.close()

        self.send_json({"error": "Rota nao encontrada"}, 404)

    def do_POST(self):
        if self.path == "/api/reimport":
            result = import_all(SOURCE_DIR)
            return self.send_json(result)
        if self.path == "/api/app-context":
            length = int(self.headers.get("Content-Length", "0") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            uf = str(payload.get("active_uf", "SC")).strip().upper()
            if len(uf) != 2:
                return self.send_json({"error": "UF invalida"}, 400)
            conn = connect()
            try:
                set_setting(conn, "active_uf", uf)
            finally:
                conn.close()
            return self.send_json({"active_uf": uf})
        if self.path == "/api/works":
            length = int(self.headers.get("Content-Length", "0") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            name = str(payload.get("name", "")).strip()
            if not name:
                return self.send_json({"error": "Nome da obra obrigatorio"}, 400)
            uf = str(payload.get("uf", "SC")).strip().upper()
            client = str(payload.get("client", "")).strip()
            conn = connect()
            try:
                cur = conn.execute(
                    "INSERT INTO works (name, client, uf) VALUES (?, ?, ?)",
                    (name, client, uf),
                )
                work_id = int(cur.lastrowid)
                set_setting(conn, "active_work_id", str(work_id))
                set_setting(conn, "active_uf", uf)
                work = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
            finally:
                conn.close()
            return self.send_json({"work": dict(work)})
        if self.path == "/api/work-items":
            length = int(self.headers.get("Content-Length", "0") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            work_id = int(payload.get("work_id") or 0)
            item_id = int(payload.get("item_id") or 0)
            quantity = float(payload.get("quantity") or 1)
            conn = connect()
            try:
                if work_id == 0:
                    work = active_work(conn)
                    if not work:
                        return self.send_json({"error": "Crie uma obra antes de adicionar itens"}, 400)
                    work_id = work["id"]
                unit_price, total_price = recalc_work_item(conn, work_id, item_id, quantity)
                cur = conn.execute(
                    """
                    INSERT INTO work_items (work_id, item_id, quantity, unit_price, total_price)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (work_id, item_id, quantity, unit_price, total_price),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM work_items WHERE id = ?", (cur.lastrowid,)).fetchone()
            finally:
                conn.close()
            return self.send_json({"item": dict(row)})
        if self.path == "/api/equivalence-status":
            length = int(self.headers.get("Content-Length", "0") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            equivalence_id = int(payload.get("id") or 0)
            status = str(payload.get("status") or "").strip().lower()
            sinapi_code = str(payload.get("sinapi_code") or "").strip()
            if status not in {"approved", "rejected", "pending", "suggested"}:
                return self.send_json({"error": "Status invalido"}, 400)
            conn = connect()
            try:
                sinapi_item = None
                if status == "approved":
                    if sinapi_code:
                        sinapi_item = conn.execute(
                            """
                            SELECT ui.id, ui.external_code, ui.description
                            FROM unified_items ui
                            JOIN data_sources ds ON ds.id = ui.source_id
                            WHERE ds.kind = 'SINAPI'
                              AND ui.kind = 'INSUMO'
                              AND ui.external_code = ?
                            ORDER BY ds.id DESC
                            LIMIT 1
                            """,
                            (sinapi_code,),
                        ).fetchone()
                        if not sinapi_item:
                            return self.send_json({"error": "Codigo SINAPI nao encontrado"}, 404)
                        conn.execute(
                            """
                            UPDATE input_equivalences
                            SET status = 'approved',
                                sinapi_item_id = ?,
                                sinapi_code = ?,
                                notes = ?,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                            """,
                            (sinapi_item["id"], sinapi_item["external_code"], sinapi_item["description"], equivalence_id),
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE input_equivalences
                            SET status = 'approved', updated_at = CURRENT_TIMESTAMP
                            WHERE id = ? AND sinapi_item_id IS NOT NULL
                            """,
                            (equivalence_id,),
                        )
                else:
                    conn.execute(
                        """
                        UPDATE input_equivalences
                        SET status = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (status, equivalence_id),
                    )
                conn.commit()
                row = conn.execute("SELECT * FROM input_equivalences WHERE id = ?", (equivalence_id,)).fetchone()
            finally:
                conn.close()
            if not row:
                return self.send_json({"error": "Equivalencia nao encontrada"}, 404)
            return self.send_json({"equivalence": dict(row)})
        self.send_json({"error": "Rota nao encontrada"}, 404)

    def log_message(self, format, *args):
        return


def main():
    log("Iniciando servidor SOO/PROENG")
    import_result = ensure_database()
    if import_result:
        print("Base importada:")
        for item in import_result["files"]:
            print(f"  {item['status']:7} {item['rows']:5} {item['file']}")
    print(f"SOO/PROENG novo rodando em http://{HOST}:{PORT}")
    log(f"Servidor pronto em http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(traceback.format_exc())
        raise
