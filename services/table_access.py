# services/table_access.py
"""
SQLite DAO for functions table.

- init_db(): 테이블이 없으면 생성
- get_function_by_key(): function_key로 단일 레코드 조회
- upsert_function(): 편의상 추가/갱신
- list_functions(): 관리용 조회

환경변수:
  APP_DB_PATH (기본값: "app.db")
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional, Dict, Any, List, Tuple
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


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """
    functions 테이블 생성(없으면).
    """
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS functions (
                function_key   TEXT PRIMARY KEY,
                script_path    TEXT,
                script_command TEXT,
                shell          TEXT,
                shortcut       TEXT
            )
            """
        )
        conn.commit()


def get_function_by_key(function_key: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """
    function_key로 단일 레코드 조회.
    반환: dict 또는 None
    """
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT function_key, script_path, script_command, shortcut
            FROM functions
            WHERE function_key = ?
            LIMIT 1
            """,
            (function_key,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


# -------- 아래는 편의용(선택) --------

def upsert_function(
    function_key: str,
    script_path: Optional[str] = None,
    script_command: Optional[str] = None,
    shell: Optional[str] = None,
    shortcut: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """
    관리 편의를 위한 upsert. (있으면 업데이트, 없으면 삽입)
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
                   SET script_path = ?,
                       script_command = ?,
                       shell = ?,
                       shortcut = ?
                 WHERE function_key = ?
                """,
                (script_path, script_command, shell, shortcut, function_key),
            )
        else:
            conn.execute(
                """
                INSERT INTO functions (function_key, script_path, script_command, shell, shortcut)
                VALUES (?, ?, ?, ?, ?)
                """,
                (function_key, script_path, script_command, shell, shortcut),
            )
        conn.commit()


def list_functions(limit: int = 100, offset: int = 0, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """
    관리 화면 등에서 사용하기 위한 간단한 목록 조회.
    """
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT function_key, script_path, script_command, shell, shortcut
            FROM functions
            ORDER BY function_key
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
