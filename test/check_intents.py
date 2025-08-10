#!/usr/bin/env python3
import sqlite3

def check_intents():
    conn = sqlite3.connect('assistant.db')
    
    # intents 테이블 구조 확인
    cursor = conn.execute("PRAGMA table_info(intents)")
    columns = cursor.fetchall()
    print("intents 테이블 구조:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    # intents 테이블 데이터 확인
    cursor = conn.execute("SELECT * FROM intents LIMIT 10")
    rows = cursor.fetchall()
    print(f"\nintents 테이블 데이터 (처음 10개):")
    for row in rows:
        print(f"  {row}")
    
    # functions 테이블과의 JOIN 확인
    cursor = conn.execute("""
        SELECT i.id, i.intent, i.function_id, f.function_key, f.function_name
        FROM intents i
        LEFT JOIN functions f ON i.function_id = f.id
        LIMIT 10
    """)
    rows = cursor.fetchall()
    print(f"\nintents + functions JOIN 결과 (처음 10개):")
    for row in rows:
        print(f"  ID: {row[0]}, Intent: {row[1]}, Function_ID: {row[2]}, Function_Key: {row[3]}, Function_Name: {row[4]}")
    
    # 파일 복사 관련 데이터 확인
    cursor = conn.execute("""
        SELECT i.id, i.intent, i.function_id, f.function_key, f.function_name
        FROM intents i
        LEFT JOIN functions f ON i.function_id = f.id
        WHERE i.intent LIKE '%복사%'
    """)
    rows = cursor.fetchall()
    print(f"\n복사 관련 intent:")
    for row in rows:
        print(f"  {row}")
    
    conn.close()

if __name__ == "__main__":
    check_intents()
