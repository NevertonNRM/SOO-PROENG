from __future__ import annotations

from db import connect, init_db
from import_sinapi_unified import assign_classification, classify_kind


def classify_legacy_input(access_code: str, description: str) -> dict[str, str]:
    classes = classify_kind(description, "INSUMO")
    access = (access_code or "").upper()
    if access.startswith("P"):
        classes["tipo_custo"] = "material"
    elif access.startswith("M"):
        classes["tipo_custo"] = "mao_obra"
        classes["familia"] = "mao_obra"
    elif "E" in access[:2]:
        classes["tipo_custo"] = "equipamento"
        classes["familia"] = "equipamento"
    classes["origem"] = "soo"
    return classes


def import_soo() -> dict:
    conn = connect()
    init_db(conn)
    try:
        conn.execute("DELETE FROM data_sources WHERE code = 'SOO-LEGADO'")
        conn.commit()
        cur = conn.execute(
            """
            INSERT INTO data_sources
            (code, name, kind, reference, source_path)
            VALUES ('SOO-LEGADO', 'SOO/PROENG legado', 'LEGADO', 'DBF original', ?)
            """,
            ("C:\\Users\\Neverton\\Documents\\New project\\SOO-PRONEG",),
        )
        source_id = int(cur.lastrowid)
        counts = {"insumos": 0, "servicos": 0, "prices": 0, "composition_items": 0, "classifications": 0}

        for row in conn.execute("SELECT * FROM inputs ORDER BY code"):
            cur = conn.execute(
                """
                INSERT INTO unified_items
                (source_id, kind, external_code, description, unit, price_origin, legacy_access_code)
                VALUES (?, 'INSUMO', ?, ?, ?, ?, ?)
                """,
                (source_id, row["code"], row["name"], row["unit"], "SOO", row["access_code"]),
            )
            item_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO unified_prices (item_id, uf, price, reference) VALUES (?, '', ?, 'DBF original')",
                (item_id, row["price"]),
            )
            for dim, option in classify_legacy_input(row["access_code"], row["name"]).items():
                assign_classification(conn, item_id, dim, option)
                counts["classifications"] += 1
            counts["insumos"] += 1
            counts["prices"] += 1

        for row in conn.execute("SELECT * FROM services ORDER BY code"):
            cur = conn.execute(
                """
                INSERT INTO unified_items
                (source_id, kind, external_code, description, unit, group_name, price_origin,
                 legacy_access_code, legacy_item_code)
                VALUES (?, 'COMPOSICAO', ?, ?, ?, ?, ?, ?, ?)
                """,
                (source_id, row["code"], row["name"], row["unit"], "SOO", "SOO", row["access_code"], row["item"]),
            )
            item_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO unified_prices (item_id, uf, price, reference) VALUES (?, '', ?, 'DBF original')",
                (item_id, row["legacy_price"]),
            )
            classes = classify_kind(row["name"], "COMPOSICAO", "SOO")
            classes["origem"] = "soo"
            for dim, option in classes.items():
                assign_classification(conn, item_id, dim, option)
                counts["classifications"] += 1
            counts["servicos"] += 1
            counts["prices"] += 1

        item_ids = {
            (row["kind"], row["external_code"]): row["id"]
            for row in conn.execute("SELECT id, kind, external_code FROM unified_items WHERE source_id = ?", (source_id,))
        }
        for row in conn.execute(
            """
            SELECT si.service_code, si.input_code, si.quantity, i.name, i.unit
            FROM service_inputs si
            LEFT JOIN inputs i ON i.code = si.input_code
            ORDER BY si.service_code, si.position
            """
        ):
            parent_id = item_ids.get(("COMPOSICAO", row["service_code"]))
            child_id = item_ids.get(("INSUMO", row["input_code"]))
            if parent_id:
                conn.execute(
                    """
                    INSERT INTO unified_composition_items
                    (parent_item_id, child_kind, child_external_code, child_item_id, description, unit, coefficient, status)
                    VALUES (?, 'INSUMO', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        parent_id,
                        row["input_code"],
                        child_id,
                        row["name"] or "(insumo nao encontrado)",
                        row["unit"] or "",
                        row["quantity"],
                        "LEGADO",
                    ),
                )
                counts["composition_items"] += 1

        conn.commit()
        return {"source_id": source_id, "source_code": "SOO-LEGADO", **counts}
    finally:
        conn.close()


if __name__ == "__main__":
    result = import_soo()
    for key, value in result.items():
        print(f"{key}: {value}")
