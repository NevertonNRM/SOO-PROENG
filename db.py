from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "soo_proneg.sqlite"


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parameters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit TEXT,
    value REAL NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS inputs (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    access_code TEXT,
    price REAL NOT NULL DEFAULT 0,
    unit TEXT,
    price_date TEXT
);

CREATE INDEX IF NOT EXISTS idx_inputs_name ON inputs(name);
CREATE INDEX IF NOT EXISTS idx_inputs_access ON inputs(access_code);

CREATE TABLE IF NOT EXISTS taxes (
    code TEXT PRIMARY KEY,
    name TEXT,
    access_code TEXT,
    percent REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_taxes_name ON taxes(name);

CREATE TABLE IF NOT EXISTS budget_descriptions (
    code TEXT PRIMARY KEY,
    item TEXT NOT NULL,
    name TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_budget_descriptions_item ON budget_descriptions(item);

CREATE TABLE IF NOT EXISTS services (
    code TEXT PRIMARY KEY,
    item TEXT,
    name TEXT NOT NULL,
    access_code TEXT,
    unit TEXT,
    legacy_price REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_services_name ON services(name);
CREATE INDEX IF NOT EXISTS idx_services_item ON services(item);

CREATE TABLE IF NOT EXISTS service_inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_code TEXT NOT NULL,
    position INTEGER NOT NULL,
    input_code TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (service_code) REFERENCES services(code) ON DELETE CASCADE,
    UNIQUE(service_code, position)
);

CREATE INDEX IF NOT EXISTS idx_service_inputs_service ON service_inputs(service_code);
CREATE INDEX IF NOT EXISTS idx_service_inputs_input ON service_inputs(input_code);

CREATE TABLE IF NOT EXISTS service_taxes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_code TEXT NOT NULL,
    position INTEGER NOT NULL,
    tax_code TEXT NOT NULL,
    FOREIGN KEY (service_code) REFERENCES services(code) ON DELETE CASCADE,
    UNIQUE(service_code, position)
);

CREATE INDEX IF NOT EXISTS idx_service_taxes_service ON service_taxes(service_code);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    client TEXT,
    name TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    budget_date TEXT,
    responsible TEXT,
    schedule_period TEXT,
    max_period INTEGER,
    total_value REAL,
    start_date TEXT
);

CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);

CREATE TABLE IF NOT EXISTS works (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    client TEXT,
    uf TEXT NOT NULL DEFAULT 'SC',
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS work_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantity REAL NOT NULL DEFAULT 1,
    unit_price REAL NOT NULL DEFAULT 0,
    total_price REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES unified_items(id)
);

CREATE INDEX IF NOT EXISTS idx_work_items_work ON work_items(work_id);

CREATE TABLE IF NOT EXISTS input_equivalences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    legacy_item_id INTEGER NOT NULL,
    sinapi_item_id INTEGER,
    legacy_code TEXT NOT NULL,
    sinapi_code TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    match_score REAL,
    match_method TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (legacy_item_id) REFERENCES unified_items(id) ON DELETE CASCADE,
    FOREIGN KEY (sinapi_item_id) REFERENCES unified_items(id),
    UNIQUE(legacy_item_id)
);

CREATE INDEX IF NOT EXISTS idx_input_equiv_status ON input_equivalences(status);
CREATE INDEX IF NOT EXISTS idx_input_equiv_sinapi ON input_equivalences(sinapi_item_id);

CREATE TABLE IF NOT EXISTS custom_item_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    work_id INTEGER,
    uf TEXT,
    price REAL NOT NULL,
    reason TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES unified_items(id) ON DELETE CASCADE,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_custom_prices_item ON custom_item_prices(item_id);

CREATE VIEW IF NOT EXISTS resolved_composition_items AS
SELECT
    uci.id,
    uci.parent_item_id,
    uci.child_kind,
    uci.child_external_code AS original_child_code,
    uci.child_item_id AS original_child_item_id,
    COALESCE(eq.sinapi_item_id, uci.child_item_id) AS resolved_child_item_id,
    COALESCE(eq.sinapi_code, uci.child_external_code) AS resolved_child_code,
    CASE WHEN eq.sinapi_item_id IS NOT NULL AND eq.status = 'approved' THEN 1 ELSE 0 END AS was_substituted,
    uci.description,
    uci.unit,
    uci.coefficient,
    uci.status
FROM unified_composition_items uci
LEFT JOIN input_equivalences eq
    ON eq.legacy_item_id = uci.child_item_id
   AND eq.status = 'approved';

CREATE TABLE IF NOT EXISTS system_info (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    client TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    phone TEXT,
    telex TEXT,
    document TEXT,
    selected_project INTEGER
);

CREATE TABLE IF NOT EXISTS schedule_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    item TEXT,
    name TEXT,
    total REAL,
    percent REAL
);

CREATE TABLE IF NOT EXISTS schedule_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    item TEXT,
    period_number TEXT,
    percent REAL
);

CREATE TABLE IF NOT EXISTS labor_dimensions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    input_code TEXT,
    journey REAL
);

CREATE TABLE IF NOT EXISTS executed_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    service_code TEXT,
    executed_date TEXT,
    quantity REAL
);

CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    rows_imported INTEGER NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS data_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    reference TEXT,
    issue_date TEXT,
    source_path TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS unified_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    external_code TEXT NOT NULL,
    description TEXT NOT NULL,
    unit TEXT,
    group_name TEXT,
    price_origin TEXT,
    legacy_access_code TEXT,
    legacy_item_code TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (source_id) REFERENCES data_sources(id) ON DELETE CASCADE,
    UNIQUE(source_id, kind, external_code)
);

CREATE INDEX IF NOT EXISTS idx_unified_items_desc ON unified_items(description);
CREATE INDEX IF NOT EXISTS idx_unified_items_kind ON unified_items(kind);
CREATE INDEX IF NOT EXISTS idx_unified_items_source ON unified_items(source_id);

CREATE TABLE IF NOT EXISTS unified_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    uf TEXT,
    price REAL,
    percent_as REAL,
    reference TEXT,
    FOREIGN KEY (item_id) REFERENCES unified_items(id) ON DELETE CASCADE,
    UNIQUE(item_id, uf, reference)
);

CREATE INDEX IF NOT EXISTS idx_unified_prices_item ON unified_prices(item_id);

CREATE TABLE IF NOT EXISTS unified_composition_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_item_id INTEGER NOT NULL,
    child_kind TEXT NOT NULL,
    child_external_code TEXT NOT NULL,
    child_item_id INTEGER,
    description TEXT,
    unit TEXT,
    coefficient REAL,
    status TEXT,
    FOREIGN KEY (parent_item_id) REFERENCES unified_items(id) ON DELETE CASCADE,
    FOREIGN KEY (child_item_id) REFERENCES unified_items(id)
);

CREATE INDEX IF NOT EXISTS idx_unified_comp_parent ON unified_composition_items(parent_item_id);

CREATE TABLE IF NOT EXISTS classification_dimensions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    allow_multiple INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS classification_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (dimension_id) REFERENCES classification_dimensions(id) ON DELETE CASCADE,
    UNIQUE(dimension_id, code)
);

CREATE TABLE IF NOT EXISTS item_classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    option_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    confidence REAL,
    note TEXT,
    FOREIGN KEY (item_id) REFERENCES unified_items(id) ON DELETE CASCADE,
    FOREIGN KEY (option_id) REFERENCES classification_options(id) ON DELETE CASCADE,
    UNIQUE(item_id, option_id)
);

CREATE INDEX IF NOT EXISTS idx_item_classifications_item ON item_classifications(item_id);

CREATE TABLE IF NOT EXISTS classification_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension_code TEXT NOT NULL,
    option_code TEXT NOT NULL,
    match_text TEXT NOT NULL,
    applies_to_kind TEXT,
    priority INTEGER NOT NULL DEFAULT 100,
    active INTEGER NOT NULL DEFAULT 1
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    seed_managerial_classifications(conn)
    conn.commit()


def seed_managerial_classifications(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('active_uf', 'SC')"
    )
    dimensions = [
        ("tipo_custo", "Tipo de custo", "Material, mao de obra, equipamento, servico e verbas gerenciais.", 0, 1),
        ("etapa_obra", "Etapa da obra", "Agrupamento fisico/gerencial da obra.", 0, 2),
        ("familia", "Familia", "Familia tecnica do insumo ou servico.", 0, 3),
        ("incidencia", "Incidencias", "Regras de encargos, BDI, administracao e riscos.", 1, 4),
        ("origem", "Origem", "Origem economica/operacional do item.", 0, 5),
    ]
    for code, name, description, allow_multiple, sort_order in dimensions:
        conn.execute(
            """
            INSERT INTO classification_dimensions
            (code, name, description, allow_multiple, sort_order)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                allow_multiple = excluded.allow_multiple,
                sort_order = excluded.sort_order
            """,
            (code, name, description, allow_multiple, sort_order),
        )

    options = {
        "tipo_custo": [
            ("material", "Material"),
            ("mao_obra", "Mao de obra"),
            ("equipamento", "Equipamento"),
            ("servico_terceirizado", "Servico terceirizado"),
            ("composicao", "Composicao"),
            ("taxa", "Taxa"),
            ("administracao", "Administracao"),
            ("outro", "Outro"),
        ],
        "etapa_obra": [
            ("servicos_iniciais", "Servicos iniciais"),
            ("fundacao", "Fundacao"),
            ("estrutura", "Estrutura"),
            ("alvenaria", "Alvenaria"),
            ("cobertura", "Cobertura"),
            ("instalacoes", "Instalacoes"),
            ("revestimento", "Revestimento"),
            ("pintura", "Pintura"),
            ("servicos_finais", "Servicos finais"),
            ("administracao_local", "Administracao local"),
            ("nao_classificado", "Nao classificado"),
        ],
        "familia": [
            ("concreto", "Concreto"),
            ("forma", "Forma"),
            ("armacao", "Armacao"),
            ("argamassa", "Argamassa"),
            ("madeira", "Madeira"),
            ("aco", "Aco"),
            ("eletrica", "Eletrica"),
            ("hidraulica", "Hidraulica"),
            ("mao_obra", "Mao de obra"),
            ("equipamento", "Equipamento"),
            ("transporte", "Transporte"),
            ("outros", "Outros"),
        ],
        "incidencia": [
            ("encargos_sociais", "Encargos sociais"),
            ("bdi", "BDI"),
            ("administracao", "Administracao"),
            ("periculosidade", "Periculosidade"),
            ("sem_incidencia", "Sem incidencia especial"),
        ],
        "origem": [
            ("sinapi", "SINAPI"),
            ("soo", "SOO/PROENG antigo"),
            ("propria", "Propria"),
            ("fornecedor", "Fornecedor"),
            ("terceirizada", "Terceirizada"),
        ],
    }
    for dimension_code, rows in options.items():
        dimension_id = conn.execute(
            "SELECT id FROM classification_dimensions WHERE code = ?",
            (dimension_code,),
        ).fetchone()["id"]
        for order, (code, name) in enumerate(rows, 1):
            conn.execute(
                """
                INSERT INTO classification_options
                (dimension_id, code, name, sort_order)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(dimension_id, code) DO UPDATE SET
                    name = excluded.name,
                    sort_order = excluded.sort_order
                """,
                (dimension_id, code, name, order),
            )


def reset_imported_data(conn: sqlite3.Connection) -> None:
    tables = [
        "executed_services",
        "labor_dimensions",
        "schedule_periods",
        "schedule_items",
        "system_info",
        "projects",
        "service_taxes",
        "service_inputs",
        "services",
        "budget_descriptions",
        "taxes",
        "inputs",
        "parameters",
        "import_log",
        "metadata",
    ]
    for table in tables:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
