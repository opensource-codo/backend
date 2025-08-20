# services/table_access.py
"""
SQLite DAO for functions table (스키마 고정):
  id, function_key, function_name, script_path, shortcut, script_command

- init_db(): 테이블 없으면 생성 (네가 제공한 스키마 그대로)
- get_function_by_key(): function_key로 단일 레코드 조회
- upsert_function(): function_key 기준 UPSERT
- list_functions(): 간단한 목록 조회

환경변수:
  APP_DB_PATH (기본값: "./db/assistant.db")
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

DEFAULT_DB_PATH = os.getenv("APP_DB_PATH", "./db/assistant.db")


@contextmanager
def _connect(db_path: str = DEFAULT_DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row  # dict(row) 가능
        yield conn
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """
    현재 스키마와 다르면 건드리지 않고,
    'functions' 테이블이 없을 때만 생성한다.
    """
    with _connect(db_path) as conn:
        if not _table_exists(conn, "functions"):
            conn.execute(
                """
                CREATE TABLE functions (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    function_key   TEXT UNIQUE,
                    function_name  TEXT NOT NULL,
                    script_path    TEXT,
                    shortcut       TEXT,
                    script_command TEXT
                )
                """
            )
            conn.commit()


def get_function_by_key(function_key: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT
                id,
                function_key,
                function_name,
                script_path,
                shortcut,
                script_command
            FROM functions
            WHERE function_key = ?
            LIMIT 1
            """,
            (function_key,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def upsert_function(
    function_key: str,
    function_name: str,
    *,
    script_path: Optional[str] = None,
    script_command: Optional[str] = None,
    shortcut: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    with _connect(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM functions WHERE function_key = ? LIMIT 1", (function_key,)
        ).fetchone()

        if exists:
            conn.execute(
                """
                UPDATE functions
                   SET function_name  = ?,
                       script_path    = ?,
                       script_command = ?,
                       shortcut       = ?
                 WHERE function_key   = ?
                """,
                (function_name, script_path, script_command, shortcut, function_key),
            )
        else:
            conn.execute(
                """
                INSERT INTO functions
                    (function_key, function_name, script_path, script_command, shortcut)
                VALUES
                    (?, ?, ?, ?, ?)
                """,
                (function_key, function_name, script_path, script_command, shortcut),
            )
        conn.commit()


def list_functions(
    limit: int = 100,
    offset: int = 0,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT
                id,
                function_key,
                function_name,
                script_path,
                script_command,
                shortcut
            FROM functions
            ORDER BY function_key
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
