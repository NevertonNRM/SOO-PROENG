from __future__ import annotations

import sqlite3
from pathlib import Path

from db import connect, init_db


ROOT = Path(__file__).resolve().parent
SINAPI_DB = ROOT.parent / "sinapi_budget_app" / "data" / "sinapi.sqlite"


def read_meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM metadata")}


def get_option_id(conn: sqlite3.Connection, dimension_code: str, option_code: str) -> int:
    row = conn.execute(
        """
        SELECT o.id
        FROM classification_options o
        JOIN classification_dimensions d ON d.id = o.dimension_id
        WHERE d.code = ? AND o.code = ?
        """,
        (dimension_code, option_code),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Opcao gerencial nao encontrada: {dimension_code}/{option_code}")
    return int(row["id"])


def classify_kind(description: str, kind: str, group_name: str = "") -> dict[str, str]:
    text = f"{description or ''} {group_name or ''}".upper()
    result = {
        "tipo_custo": "composicao" if kind == "COMPOSICAO" else "outro",
        "etapa_obra": "nao_classificado",
        "familia": "outros",
        "origem": "sinapi",
    }

    if kind == "INSUMO":
        if any(word in text for word in ["PEDREIRO", "SERVENTE", "CARPINTEIRO", "ELETRICISTA", "ENCANADOR", "PINTOR", "ARMADOR", "OPERADOR", "MESTRE"]):
            result["tipo_custo"] = "mao_obra"
            result["familia"] = "mao_obra"
        elif any(word in text for word in ["CAMINHAO", "BETONEIRA", "GUINCHO", "ESCAVADEIRA", "COMPACTADOR", "VIBRADOR", "EQUIPAMENTO", "MAQUINA"]):
            result["tipo_custo"] = "equipamento"
            result["familia"] = "equipamento"
        else:
            result["tipo_custo"] = "material"

    family_rules = [
        ("concreto", ["CONCRETO", "CIMENTO", "BRITA"]),
        ("forma", ["FORMA", "FORMAS", "COMPENSADO"]),
        ("armacao", ["ARMACAO", "ARMAÇÃO", "ACO CA", "AÇO CA", "VERGALHAO", "VERGALHÃO"]),
        ("argamassa", ["ARGAMASSA", "REJUNTE", "CHAPISCO", "EMBOCO", "EMBOÇO"]),
        ("madeira", ["MADEIRA", "TABUA", "TÁBUA", "PONTALETE", "SARRAFO"]),
        ("eletrica", ["ELETRIC", "ELETRODUTO", "CABO", "DISJUNTOR", "LUMINARIA", "LUMINÁRIA"]),
        ("hidraulica", ["HIDRAUL", "TUBO", "ESGOTO", "AGUA FRIA", "ÁGUA FRIA", "PVC"]),
        ("transporte", ["TRANSPORTE", "CARGA", "DESCARGA", "CAMINHAO", "CAMINHÃO"]),
    ]
    for option, words in family_rules:
        if any(word in text for word in words):
            result["familia"] = option
            break

    stage_rules = [
        ("servicos_iniciais", ["LIMPEZA", "TAPUME", "CANTEIRO", "LOCACAO", "LOCAÇÃO", "DEMOLICAO", "DEMOLIÇÃO"]),
        ("fundacao", ["FUNDACAO", "FUNDAÇÃO", "SAPATA", "ESTACA", "BALDRAME", "ESCAVACAO", "ESCAVAÇÃO"]),
        ("estrutura", ["ESTRUTURA", "PILAR", "VIGA", "LAJE", "CONCRETO ARMADO"]),
        ("alvenaria", ["ALVENARIA", "BLOCO", "TIJOLO", "PAREDE"]),
        ("cobertura", ["COBERTURA", "TELHA", "TELHADO", "CALHA", "RUFO"]),
        ("instalacoes", ["ELETRIC", "HIDRAUL", "SANITAR", "ESGOTO", "PLUVIAL"]),
        ("revestimento", ["REVESTIMENTO", "CHAPISCO", "EMBOCO", "EMBOÇO", "REBOCO", "CERAMICA", "CERÂMICA"]),
        ("pintura", ["PINTURA", "TINTA", "SELADOR", "MASSA ACRILICA", "MASSA ACRÍLICA"]),
        ("servicos_finais", ["LIMPEZA FINAL", "ARREMATE"]),
        ("administracao_local", ["ADMINISTRACAO LOCAL", "ADMINISTRAÇÃO LOCAL"]),
    ]
    for option, words in stage_rules:
        if any(word in text for word in words):
            result["etapa_obra"] = option
            break

    return result


def assign_classification(conn: sqlite3.Connection, item_id: int, dimension_code: str, option_code: str, source: str = "auto") -> None:
    option_id = get_option_id(conn, dimension_code, option_code)
    conn.execute(
        """
        INSERT OR IGNORE INTO item_classifications
        (item_id, option_id, source, confidence, note)
        VALUES (?, ?, ?, ?, ?)
        """,
        (item_id, option_id, source, 0.65 if source == "auto" else 1.0, "Classificacao inicial por regras de texto"),
    )


def import_sinapi(sinapi_db: Path = SINAPI_DB) -> dict:
    if not sinapi_db.exists():
        raise FileNotFoundError(f"Banco SINAPI nao encontrado: {sinapi_db}")

    source = sqlite3.connect(sinapi_db)
    source.row_factory = sqlite3.Row
    target = connect()
    init_db(target)
    try:
        meta = read_meta(source)
        reference = meta.get("reference_month", "")
        source_code = f"SINAPI-{reference}".replace("/", "-") if reference else "SINAPI"

        target.execute("DELETE FROM data_sources WHERE code = ?", (source_code,))
        target.commit()

        cur = target.execute(
            """
            INSERT INTO data_sources
            (code, name, kind, reference, issue_date, source_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_code,
                f"SINAPI {reference}".strip(),
                "SINAPI",
                reference,
                meta.get("issue_date", ""),
                str(sinapi_db),
            ),
        )
        source_id = int(cur.lastrowid)

        counts = {"insumos": 0, "composicoes": 0, "prices": 0, "composition_items": 0, "classifications": 0}

        for row in source.execute("SELECT code, classification, description, unit, price_origin FROM insumos"):
            cur = target.execute(
                """
                INSERT INTO unified_items
                (source_id, kind, external_code, description, unit, group_name, price_origin)
                VALUES (?, 'INSUMO', ?, ?, ?, ?, ?)
                """,
                (source_id, row["code"], row["description"], row["unit"], row["classification"], row["price_origin"]),
            )
            item_id = int(cur.lastrowid)
            classes = classify_kind(row["description"], "INSUMO", row["classification"])
            for dim, option in classes.items():
                assign_classification(target, item_id, dim, option)
                counts["classifications"] += 1
            counts["insumos"] += 1

        for row in source.execute("SELECT code, group_name, description, unit FROM composicoes"):
            cur = target.execute(
                """
                INSERT INTO unified_items
                (source_id, kind, external_code, description, unit, group_name)
                VALUES (?, 'COMPOSICAO', ?, ?, ?, ?)
                """,
                (source_id, row["code"], row["description"], row["unit"], row["group_name"]),
            )
            item_id = int(cur.lastrowid)
            classes = classify_kind(row["description"], "COMPOSICAO", row["group_name"])
            for dim, option in classes.items():
                assign_classification(target, item_id, dim, option)
                counts["classifications"] += 1
            counts["composicoes"] += 1

        item_ids = {
            (row["kind"], row["external_code"]): row["id"]
            for row in target.execute("SELECT id, kind, external_code FROM unified_items WHERE source_id = ?", (source_id,))
        }

        for row in source.execute("SELECT code, uf, price FROM insumo_prices"):
            item_id = item_ids.get(("INSUMO", row["code"]))
            if item_id:
                target.execute(
                    "INSERT INTO unified_prices (item_id, uf, price, reference) VALUES (?, ?, ?, ?)",
                    (item_id, row["uf"], row["price"], reference),
                )
                counts["prices"] += 1

        for row in source.execute("SELECT code, uf, cost, percent_as FROM composicao_prices"):
            item_id = item_ids.get(("COMPOSICAO", row["code"]))
            if item_id:
                target.execute(
                    "INSERT INTO unified_prices (item_id, uf, price, percent_as, reference) VALUES (?, ?, ?, ?, ?)",
                    (item_id, row["uf"], row["cost"], row["percent_as"], reference),
                )
                counts["prices"] += 1

        for row in source.execute("SELECT composition_code, item_type, item_code, description, unit, coefficient, status FROM analitico_items"):
            parent_id = item_ids.get(("COMPOSICAO", row["composition_code"]))
            child_kind = "COMPOSICAO" if row["item_type"] == "COMPOSICAO" else "INSUMO"
            child_id = item_ids.get((child_kind, row["item_code"]))
            if parent_id:
                target.execute(
                    """
                    INSERT INTO unified_composition_items
                    (parent_item_id, child_kind, child_external_code, child_item_id, description, unit, coefficient, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        parent_id,
                        child_kind,
                        row["item_code"],
                        child_id,
                        row["description"],
                        row["unit"],
                        row["coefficient"],
                        row["status"],
                    ),
                )
                counts["composition_items"] += 1

        target.commit()
        return {"source_id": source_id, "source_code": source_code, "reference": reference, **counts}
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    result = import_sinapi()
    for key, value in result.items():
        print(f"{key}: {value}")
