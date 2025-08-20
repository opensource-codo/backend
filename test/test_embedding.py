#!/usr/bin/env python3
"""
ChromaDB 임베딩 테스트 스크립트
"""
import sys
import os

# 현재 파일의 디렉토리에서 상위 디렉토리로 이동하여 backend 폴더를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from services.table_embedding import ChromaDBEmbedding, create_embedding_instance, search_intent_from_query

def test_embedding():
    """임베딩 기능을 테스트합니다."""
    print("=== ChromaDB 임베딩 테스트 시작 ===")
    
    try:
        # 임베딩 인스턴스 생성 및 데이터 로드
        print("1. 임베딩 인스턴스 생성 중...")
        embedding_db = create_embedding_instance()
        
        # 검색 테스트
        print("\n2. 검색 테스트 시작...")
        test_queries = [
            "스크린 캡처 어떻게 해?",
            "제어판 열어줘",
            "파일 복사해줘",
            "파일 붙여넣기 어떻게 해?",
            "파일 잘라내기 실행해줘"
        ]
        
        for query in test_queries:
            print(f"\n쿼리: '{query}'")
            res = embedding_db.find_best_intent(query=query, top_k=30)

            if not res.get("ok"):
                print("  검색 실패:", res.get("message"))
                continue

            top = res.get("top_intent")
            if not top:
                print("  후보 없음")
                continue

            print(f"  [TOP] 의도: {top['intent']} | 함수키: {top['function_key']} | 점수(sim): {top['score']:.3f}")
            print(f"  상태: {res['status']}  (threshold={res['debug']['threshold']})")

            # 후보 몇 개 더 보기
            print("  후보 상위:")
            for i, c in enumerate(res.get("candidates", [])[0:5], 1):
                print(f"    {i}. 의도: {c['intent']} | 함수키: {c['function_key']} | 점수(sim): {c['score']:.3f} | views: {','.join(c['views'])}")
                
        print("=== 테스트 완료 ===")
        
    except Exception as e:
        print(f"테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_embedding()
    # test_specific_collection_search() 