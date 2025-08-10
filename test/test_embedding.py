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
            "파일을 삭제하고 싶어",
            "파일을 복사해줘",
            "제어판 보여줘",
            "캡쳐해줘",
            "붙여넣기 해줘"
        ]
        
        for query in test_queries:
            print(f"\n쿼리: '{query}'")
            results = embedding_db.search_intent(query, n_results=1)
            # print(results)
            for i, result in enumerate(results, 1):
                metadata = result['metadata']
                distance = result['distance']
                print(f"  {i}. 유사도: {1 - distance:.3f}")
                print(f"     타입: {metadata.get('type', 'unknown')}")
                print(f"     의도: {metadata.get('intent', 'N/A')}")
                print(f"     함수: {metadata.get('function_name', 'N/A')}")
                print(f"     함수키: {metadata.get('function_key', 'N/A')}")
                print(f"     도움말: {metadata.get('help_text', 'N/A')[:50]}...")
                # if metadata.get('type') == 'intent':
                #     print(f"     의도: {metadata.get('intent', 'N/A')}")
                #     print(f"     함수: {metadata.get('function_name', 'N/A')}")
                # elif metadata.get('type') == 'function':
                #     print(f"     함수명: {metadata.get('function_name', 'N/A')}")
                #     print(f"     함수키: {metadata.get('function_key', 'N/A')}")
                # elif metadata.get('type') == 'help_content':
                #     print(f"     도움말: {metadata.get('help_text', 'N/A')[:50]}...")
                print()
        
        print("=== 테스트 완료 ===")
        
    except Exception as e:
        print(f"테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_embedding()
    # test_specific_collection_search() 