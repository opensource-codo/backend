import sqlite3
from sqlite3 import Connection

DB_PATH = "intents.db"

def get_db_connection() -> Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_required_params(intent: str):
    conn = get_db_connection()
    cursor = conn.execute("SELECT param FROM required_params WHERE intent = ?", (intent,))
    rows = cursor.fetchall()
    conn.close()
    return [row["param"] for row in rows]
