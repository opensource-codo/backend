#!/usr/bin/env python3
import sqlite3

def check_db():
    conn = sqlite3.connect('assistant.db')
    
    # 테이블 목록 확인
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("테이블 목록:")
    for table in tables:
        print(f"  - {table[0]}")
    
    # functions 테이블 구조 확인
    try:
        cursor = conn.execute("PRAGMA table_info(functions)")
        columns = cursor.fetchall()
        print("\nfunctions 테이블 구조:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
    except:
        print("\nfunctions 테이블이 없습니다.")
    
    # intent_params 테이블이 있는지 확인
    try:
        cursor = conn.execute("PRAGMA table_info(intent_params)")
        columns = cursor.fetchall()
        print("\nintent_params 테이블 구조:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
    except:
        print("\nintent_params 테이블이 없습니다.")
    
    # functions 테이블 샘플 데이터
    try:
        cursor = conn.execute("SELECT * FROM functions LIMIT 3")
        rows = cursor.fetchall()
        print("\nfunctions 테이블 샘플 데이터:")
        for row in rows:
            print(f"  {row}")
    except:
        print("\nfunctions 테이블 데이터를 읽을 수 없습니다.")
    
    conn.close()

if __name__ == "__main__":
    check_db()
