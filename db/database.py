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

def get_shortcut(function_id: str):
    conn = get_db_connection()
    cursor = conn.execute("SELECT shortcut FROM functions WHERE function_id = ?", (function_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row["shortcut"] for row in rows]

def get_function_info(intent: str):
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT f.function_id, f.shortcut 
        FROM functions f
        JOIN intents i ON f.function_id = i.function_id
        WHERE i.intent = ?
    """, (intent,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "function_id": row["function_id"],
            "shortcut": row["shortcut"]
        }
    else:
        return {
            "function_id": "",
            "shortcut": ""
        }
    
  
    