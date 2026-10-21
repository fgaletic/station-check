"""SQLite storage. Timestamps are stored as naive UTC strings 'YYYY-MM-DDTHH:MM:SS'."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("APP_DB", Path(__file__).resolve().parent.parent / "stationcheck.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS greenhouses (
    id                  INTEGER PRIMARY KEY,
    name                TEXT NOT NULL,
    lat                 REAL NOT NULL,
    lon                 REAL NOT NULL,
    company_id          TEXT NOT NULL,
    station_code        TEXT NOT NULL,
    station_name        TEXT NOT NULL,
    station_km          REAL NOT NULL,
    scenario            TEXT NOT NULL DEFAULT 'none',
    fault_start         TEXT,
    baseline_start      TEXT NOT NULL,
    baseline_end        TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    ref_sensor_id       TEXT,
    health_sensor_id    TEXT,
    source_synced_until TEXT,
    last_sync_at        TEXT,
    last_sync_error     TEXT
);
CREATE TABLE IF NOT EXISTS readings (
    greenhouse_id INTEGER NOT NULL REFERENCES greenhouses(id) ON DELETE CASCADE,
    source        TEXT NOT NULL CHECK (source IN ('farm', 'ref')),
    variable      TEXT NOT NULL,
    ts            TEXT NOT NULL,
    value         REAL NOT NULL,
    PRIMARY KEY (greenhouse_id, source, variable, ts)
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with session() as conn:
        conn.executescript(SCHEMA)


def paired_series(conn, greenhouse_id, variable, since=None):
    """[(ts, farm, ref)] for timestamps present in both sources, oldest first."""
    rows = conn.execute(
        """SELECT f.ts, f.value AS farm, r.value AS ref
             FROM readings f JOIN readings r
               ON r.greenhouse_id = f.greenhouse_id AND r.variable = f.variable AND r.ts = f.ts
            WHERE f.greenhouse_id = ? AND f.variable = ? AND f.source = 'farm' AND r.source = 'ref'
              AND f.ts >= ?
            ORDER BY f.ts""",
        (greenhouse_id, variable, since or ""),
    ).fetchall()
    return [(r["ts"], r["farm"], r["ref"]) for r in rows]
