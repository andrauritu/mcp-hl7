import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("app.db")

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    
    with get_conn() as conn:
        conn.executescript(schema_sql)