"""
Run history store.
Uses PostgreSQL when DATABASE_URL is set (add Railway Postgres plugin),
falls back to SQLite for local dev or Railway without a DB plugin.
"""
import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

DATABASE_URL = os.environ.get("DATABASE_URL")

# SQLite path: /app/data on Railway (add a volume there), local data/ dir otherwise
_SQLITE_DIR = (
    Path("/app/data")
    if os.environ.get("RAILWAY_ENVIRONMENT")
    else Path(__file__).parent.parent / "data"
)
_SQLITE_PATH = _SQLITE_DIR / "dwt.db"


def _conn():
    """Return (connection, is_postgres)."""
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL), True
    _SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_SQLITE_PATH))
    c.row_factory = sqlite3.Row
    return c, False


def init_db():
    conn, pg = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id           TEXT PRIMARY KEY,
                workflow     TEXT NOT NULL,
                status       TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                completed_at TEXT,
                topic        TEXT,
                result_json  TEXT,
                error        TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def save_run(run_id: str, workflow: str, status: str,
             topic: Optional[str] = None,
             result: Optional[dict] = None,
             error: Optional[str] = None):
    now = datetime.utcnow().isoformat()
    fin = now if status in ("complete", "failed") else None
    rj  = json.dumps(result) if result else None
    conn, pg = _conn()
    ph = "%s" if pg else "?"
    try:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO runs (id, workflow, status, created_at, completed_at, topic, result_json, error)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
            ON CONFLICT(id) DO UPDATE SET
                status       = excluded.status,
                completed_at = excluded.completed_at,
                topic        = excluded.topic,
                result_json  = excluded.result_json,
                error        = excluded.error
        """, (run_id, workflow, status, now, fin, topic, rj, error))
        conn.commit()
    finally:
        conn.close()


def get_runs(workflow: Optional[str] = None, limit: int = 100) -> List[Dict]:
    conn, pg = _conn()
    ph = "%s" if pg else "?"
    try:
        if pg:
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cur = conn.cursor()

        if workflow:
            cur.execute(
                f"SELECT * FROM runs WHERE workflow={ph} ORDER BY created_at DESC LIMIT {ph}",
                (workflow, limit),
            )
        else:
            cur.execute(
                f"SELECT * FROM runs ORDER BY created_at DESC LIMIT {ph}",
                (limit,),
            )

        rows = []
        for row in cur.fetchall():
            d = dict(row)
            rj = d.pop("result_json", None)
            d["result"] = json.loads(rj) if rj else {}
            rows.append(d)
        return rows
    finally:
        conn.close()
