from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from collections import defaultdict

from db import connect, init_db


STOPWORDS = {
    "DE",
    "DA",
    "DO",
    "DAS",
    "DOS",
    "COM",
    "SEM",
    "PARA",
    "EM",
    "E",
    "A",
    "O",
    "AS",
    "OS",
    "C",
    "P",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    words = [word for word in text.split() if word not in STOPWORDS]
    return " ".join(words)


def tokens(text: str) -> set[str]:
    return {word for word in normalize(text).split() if len(word) > 2}


def score_match(legacy_name: str, sinapi_name: str) -> float:
    legacy_norm = normalize(legacy_name)
    sinapi_norm = normalize(sinapi_name)
    if not legacy_norm or not sinapi_norm:
        return 0
    legacy_tokens = tokens(legacy_name)
    sinapi_tokens = tokens(sinapi_name)
    overlap = len(legacy_tokens & sinapi_tokens) / max(1, len(legacy_tokens | sinapi_tokens))
    ratio = SequenceMatcher(None, legacy_norm, sinapi_norm).ratio()
    starts = 0.12 if sinapi_norm.startswith(legacy_norm) or legacy_norm.startswith(sinapi_norm) else 0
    return min(1.0, overlap * 0.55 + ratio * 0.33 + starts)


def generate(limit_candidates: int = 8) -> dict:
    conn = connect()
    init_db(conn)
    try:
        legacy_source = conn.execute("SELECT id FROM data_sources WHERE code = 'SOO-LEGADO'").fetchone()
        sinapi_source = conn.execute("SELECT id FROM data_sources WHERE code LIKE 'SINAPI-%' ORDER BY id DESC LIMIT 1").fetchone()
        if not legacy_source or not sinapi_source:
            raise RuntimeError("Importe SOO-LEGADO e SINAPI antes de gerar equivalencias.")

        legacy_inputs = conn.execute(
            """
            SELECT id, external_code, description, unit
            FROM unified_items
            WHERE source_id = ? AND kind = 'INSUMO'
            ORDER BY external_code
            """,
            (legacy_source["id"],),
        ).fetchall()
        sinapi_inputs = conn.execute(
            """
            SELECT id, external_code, description, unit
            FROM unified_items
            WHERE source_id = ? AND kind = 'INSUMO'
            ORDER BY external_code
            """,
            (sinapi_source["id"],),
        ).fetchall()

        sinapi_by_token = defaultdict(list)
        for sinapi in sinapi_inputs:
            for token in tokens(sinapi["description"]):
                sinapi_by_token[token].append(sinapi)

        created = 0
        strong = 0
        for legacy in legacy_inputs:
            best = []
            legacy_tokens = tokens(legacy["description"])
            candidates = {}
            for token in legacy_tokens:
                for sinapi in sinapi_by_token.get(token, []):
                    candidates[sinapi["id"]] = sinapi
            for sinapi in candidates.values():
                if legacy["unit"] and sinapi["unit"] and legacy["unit"].upper() != sinapi["unit"].upper():
                    unit_bonus = -0.08
                else:
                    unit_bonus = 0.08
                score = score_match(legacy["description"], sinapi["description"]) + unit_bonus
                if score > 0.36:
                    best.append((score, sinapi))
            best.sort(key=lambda item: item[0], reverse=True)
            candidate = best[0] if best else (None, None)
            score, sinapi = candidate
            status = "suggested" if sinapi else "pending"
            if score and score >= 0.78:
                strong += 1
            conn.execute(
                """
                INSERT INTO input_equivalences
                (legacy_item_id, sinapi_item_id, legacy_code, sinapi_code, status, match_score, match_method, notes)
                VALUES (?, ?, ?, ?, ?, ?, 'text_similarity', ?)
                ON CONFLICT(legacy_item_id) DO UPDATE SET
                    sinapi_item_id = excluded.sinapi_item_id,
                    sinapi_code = excluded.sinapi_code,
                    status = CASE WHEN input_equivalences.status = 'approved' THEN input_equivalences.status ELSE excluded.status END,
                    match_score = excluded.match_score,
                    match_method = excluded.match_method,
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    legacy["id"],
                    None if not sinapi else sinapi["id"],
                    legacy["external_code"],
                    None if not sinapi else sinapi["external_code"],
                    status,
                    score,
                    None if not sinapi else f"{sinapi['description']} ({sinapi['unit'] or '-'})",
                ),
            )
            created += 1
        conn.commit()
        return {"legacy_inputs": len(legacy_inputs), "sinapi_inputs": len(sinapi_inputs), "equivalences": created, "strong_suggestions": strong}
    finally:
        conn.close()


if __name__ == "__main__":
    result = generate()
    for key, value in result.items():
        print(f"{key}: {value}")
