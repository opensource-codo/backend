# services/table_access.py
"""
SQLite DAO for functions table.

- init_db(): 테이블 존재 여부 및 스키마 점검(없으면 생성, shell 컬럼 없으면 추가)
- get_function_by_key(): function_key로 단일 레코드 조회
- upsert_function(): function_key 기반 UPSERT
- list_functions(): 관리용 조회

환경변수:
  APP_DB_PATH (기본값: "assistant.db")
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

DEFAULT_DB_PATH = os.getenv("APP_DB_PATH", "assistant.db")


@contextmanager
def _connect(db_path: str = DEFAULT_DB_PATH):
    """
    매 호출마다 연결을 열고 닫는다(간단/안전).
    FastAPI에서는 요청 단위로 열었다 닫는 방식이 관리가 쉽다.
    """
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


def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    cols = {row["name"] for row in info}
    return col in cols


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """
    현재 DB 스키마에 맞춰 안전하게 초기화/보수.
    - functions 테이블이 없으면 생성(네가 보여준 스키마 기준)
    - shell 컬럼이 없으면 ALTER로 추가
    """
    with _connect(db_path) as conn:
        if not _table_exists(conn, "functions"):
            # 네 DB에 이미 존재하는 스키마를 기준으로 생성
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

        # shell 컬럼이 없으면 추가(선택 사용)
        if not _has_column(conn, "functions", "shell"):
            conn.execute("ALTER TABLE functions ADD COLUMN shell TEXT")
            conn.commit()


def get_function_by_key(function_key: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """
    function_key로 단일 레코드 조회.
    반환: dict 또는 None
    """
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT
                id,
                function_key,
                function_name,
                script_path,
                shortcut,
                script_command,
                shell
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
    shell: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """
    관리 편의를 위한 upsert. (function_key 기준)
    """
    with _connect(db_path) as conn:
        # 존재 여부 확인
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
                       shortcut       = ?,
                       shell          = ?
                 WHERE function_key   = ?
                """,
                (function_name, script_path, script_command, shortcut, shell, function_key),
            )
        else:
            conn.execute(
                """
                INSERT INTO functions
                    (function_key, function_name, script_path, script_command, shortcut, shell)
                VALUES
                    (?, ?, ?, ?, ?, ?)
                """,
                (function_key, function_name, script_path, script_command, shortcut, shell),
            )
        conn.commit()


def list_functions(
    limit: int = 100,
    offset: int = 0,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """
    관리 화면 등에서 사용하기 위한 간단한 목록 조회.
    """
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT
                id,
                function_key,
                function_name,
                script_path,
                script_command,
                shortcut,
                shell
            FROM functions
            ORDER BY function_key
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
