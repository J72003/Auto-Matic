"""SQLite connection management and schema/seed setup.

A thin module so the rest of the app never builds raw connections itself.
The DB path is configurable via the DATABASE_PATH env var, which makes it
easy to point at an ephemeral file in tests and a persistent disk in prod.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Iterator

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dealerlot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    make         TEXT    NOT NULL,
    model        TEXT    NOT NULL,
    year         INTEGER NOT NULL,
    mileage      INTEGER NOT NULL,
    condition    INTEGER NOT NULL CHECK (condition BETWEEN 1 AND 5),
    accidents    INTEGER NOT NULL DEFAULT 0,
    asking_price INTEGER NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'available',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    intake_date  TEXT    NOT NULL DEFAULT (date('now')),
    cost_basis   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_vehicles_status ON vehicles(status);
"""

# (make, model, year, mileage, condition, accidents, asking_price, status, intake_days_ago, cost_basis)
# intake_days_ago produces a realistic spread: Fresh(5), Aging(1), Stale(2), Critical(2) available
_SEED_DATA = [
    ("Ford",       "F-150",          2019, 71000, 3, 1, 17700, "available", 64, 15000),
    ("Toyota",     "Camry",          2021, 38000, 4, 0, 24100, "available", 12, 20500),
    ("Jeep",       "Grand Cherokee", 2020, 60000, 3, 2, 16200, "available", 48, 13800),
    ("Nissan",     "Altima",         2017, 99000, 2, 1, 11200, "available", 35,  9500),
    ("Tesla",      "Model 3",        2022, 29000, 5, 0, 29400, "available",  8, 25000),
    ("Subaru",     "Outback",        2019, 66000, 4, 0, 14100, "available", 52, 12000),
    ("Honda",      "CR-V",           2020, 52000, 4, 0, 17400, "available", 28, 14800),
    ("Chevrolet",  "Equinox",        2018, 88000, 2, 1, 12100, "available", 62, 10300),
    ("Honda",      "Civic",          2021, 41000, 4, 0, 20000, "available", 20, 17000),
    ("Hyundai",    "Tucson",         2022, 22000, 5, 0, 17300, "available",  5, 14700),
    ("Ford",       "Escape",         2020, 57000, 3, 0, 16700, "sold",      40, 14200),
    ("Mazda",      "CX-5",           2019, 48000, 4, 0, 12800, "sold",      15, 10900),
]


def get_db_path() -> str:
    return os.environ.get("DATABASE_PATH", DEFAULT_DB)


@contextmanager
def connect(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a connection with row access by name; commits on success."""
    conn = sqlite3.connect(db_path or get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent: add new columns to existing databases that predate this schema."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(vehicles)").fetchall()}
    if "intake_date" not in cols:
        conn.execute(
            "ALTER TABLE vehicles ADD COLUMN intake_date TEXT NOT NULL DEFAULT (date('now'))"
        )
    if "cost_basis" not in cols:
        conn.execute("ALTER TABLE vehicles ADD COLUMN cost_basis INTEGER")


def init_db(db_path: str | None = None, seed: bool = True) -> None:
    """Create the schema, run any migrations, and seed sample inventory if empty."""
    today = date.today()
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        if seed:
            count = conn.execute("SELECT COUNT(*) AS n FROM vehicles").fetchone()["n"]
            if count == 0:
                rows = [
                    (
                        make, model, year, mileage, cond, acc, price, status,
                        (today - timedelta(days=days_ago)).isoformat(),
                        cost_basis,
                    )
                    for make, model, year, mileage, cond, acc, price, status, days_ago, cost_basis
                    in _SEED_DATA
                ]
                conn.executemany(
                    """INSERT INTO vehicles
                       (make, model, year, mileage, condition, accidents, asking_price, status,
                        intake_date, cost_basis)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
