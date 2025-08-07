# db/assistantdb.py

import sqlite3
import os
from sqlite3 import Connection

# 절대 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSISTANT_DB_PATH = os.path.join(BASE_DIR, "..", "assistant.db")

def get_assistant_db() -> Connection:
    conn = sqlite3.connect(ASSISTANT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_function_info(intent: str):
    conn = get_assistant_db()
    cursor = conn.execute("""
        SELECT f.id, f.shortcut 
        FROM functions f
        JOIN intents i ON f.function_key = i.function_id
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


def get_all_functions():
    conn = get_assistant_db()
    cursor = conn.execute("SELECT * FROM functions")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_required_params(intent: str):
    conn = get_assistant_db()
    cursor = conn.execute("SELECT param FROM required_params WHERE intent = ?", (intent,))
    rows = cursor.fetchall()
    conn.close()
    return [row["param"] for row in rows]
