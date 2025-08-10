#!/usr/bin/env python3
"""
데이터베이스 연결 상태 확인 테스트 스크립트
"""
import sys
import os
import sqlite3

# 현재 파일의 디렉토리에서 상위 디렉토리로 이동하여 backend 폴더를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from db.database import get_db_connection, get_required_params, get_function_info
from db.assistantdb import get_assistant_db, get_all_functions, get_required_params as get_assistant_required_params

def test_database_connection():
    """데이터베이스 연결을 테스트합니다."""
    print("=== 데이터베이스 연결 테스트 시작 ===")
    
    # assistant.db 연결 테스트
    print("\n2. assistant.db 연결 테스트:")
    try:
        conn = get_assistant_db()
        print("   ✓ assistant.db 연결 성공")
        
        # 테이블 목록 확인
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"   ✓ 테이블 목록: {[table[0] for table in tables]}")
        
        # 각 테이블의 레코드 수 확인
        for table in tables:
            table_name = table[0]
            cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"     - {table_name}: {count}개 레코드")
        
        conn.close()
        
    except Exception as e:
        print(f"   ✗ assistant.db 연결 실패: {e}")

def test_database_queries():
    """데이터베이스 쿼리 기능을 테스트합니다."""
    print("\n=== 데이터베이스 쿼리 테스트 ===")
    
    # 1. intents.db 쿼리 테스트
    print("\n1. intents.db 쿼리 테스트:")
    try:
        # required_params 테이블에서 데이터 조회
        params = get_required_params("파일 삭제")
        print(f"   ✓ '파일 삭제' 의도에 필요한 파라미터: {params}")
        
        # function_info 조회
        func_info = get_function_info("파일 삭제")
        print(f"   ✓ '파일 삭제' 의도에 대한 함수 정보: {func_info}")
        
    except Exception as e:
        print(f"   ✗ intents.db 쿼리 실패: {e}")
    
    # 2. assistant.db 쿼리 테스트
    print("\n2. assistant.db 쿼리 테스트:")
    try:
        # 모든 함수 정보 조회
        functions = get_all_functions()
        print(f"   ✓ 전체 함수 수: {len(functions)}개")
        if functions:
            print(f"   ✓ 첫 번째 함수 정보: {functions[0]}")
        
        # required_params 조회
        params = get_assistant_required_params("파일 삭제")
        print(f"   ✓ '파일 삭제' 의도에 필요한 파라미터: {params}")
        
    except Exception as e:
        print(f"   ✗ assistant.db 쿼리 실패: {e}")

def test_database_structure():
    """데이터베이스 구조를 상세히 확인합니다."""
    print("\n=== 데이터베이스 구조 상세 확인 ===")
    
    # 1. intents.db 구조 확인
    print("\n1. intents.db 구조:")
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            print(f"\n   테이블: {table_name}")
            
            # 테이블 스키마 확인
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            for col in columns:
                print(f"     - {col[1]} ({col[2]}) {'PRIMARY KEY' if col[5] else ''}")
            
            # 샘플 데이터 확인 (최대 3개)
            cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT 3")
            rows = cursor.fetchall()
            if rows:
                print(f"     샘플 데이터:")
                for i, row in enumerate(rows, 1):
                    print(f"       {i}. {dict(row)}")
            else:
                print(f"     데이터 없음")
        
        conn.close()
        
    except Exception as e:
        print(f"   ✗ intents.db 구조 확인 실패: {e}")
    
    # 2. assistant.db 구조 확인
    print("\n2. assistant.db 구조:")
    try:
        conn = get_assistant_db()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            print(f"\n   테이블: {table_name}")
            
            # 테이블 스키마 확인
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            for col in columns:
                print(f"     - {col[1]} ({col[2]}) {'PRIMARY KEY' if col[5] else ''}")
            
            # 샘플 데이터 확인 (최대 3개)
            cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT 3")
            rows = cursor.fetchall()
            if rows:
                print(f"     샘플 데이터:")
                for i, row in enumerate(rows, 1):
                    print(f"       {i}. {dict(row)}")
            else:
                print(f"     데이터 없음")
        
        conn.close()
        
    except Exception as e:
        print(f"   ✗ assistant.db 구조 확인 실패: {e}")

def test_file_existence():
    """데이터베이스 파일 존재 여부를 확인합니다."""
    print("\n=== 데이터베이스 파일 존재 확인 ===")
    
    db_files = [
        "assistant.db",
        "db/assistant.db"
    ]
    
    for db_file in db_files:
        if os.path.exists(db_file):
            size = os.path.getsize(db_file)
            print(f"   ✓ {db_file}: 존재 (크기: {size:,} bytes)")
        else:
            print(f"   ✗ {db_file}: 존재하지 않음")

if __name__ == "__main__":
    test_file_existence()
    test_database_connection()
    test_database_queries()
    test_database_structure()
    print("\n=== 데이터베이스 테스트 완료 ===") 