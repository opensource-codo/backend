#!/usr/bin/env python3
"""
ChromaDB 임베딩 테스트 스크립트
"""

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
            "도움말을 보여줘",
            "단축키 알려줘",
            "함수 실행해줘"
        ]
        
        for query in test_queries:
            print(f"\n쿼리: '{query}'")
            results = embedding_db.search_intent(query, n_results=3)
            
            for i, result in enumerate(results, 1):
                metadata = result['metadata']
                distance = result['distance']
                print(f"  {i}. 유사도: {1 - distance:.3f}")
                print(f"     타입: {metadata.get('type', 'unknown')}")
                
                if metadata.get('type') == 'intent':
                    print(f"     의도: {metadata.get('intent', 'N/A')}")
                    print(f"     함수: {metadata.get('function_name', 'N/A')}")
                    print(f"     단축키: {metadata.get('shortcut', 'N/A')}")
                elif metadata.get('type') == 'function':
                    print(f"     함수명: {metadata.get('function_name', 'N/A')}")
                    print(f"     함수키: {metadata.get('function_key', 'N/A')}")
                    print(f"     단축키: {metadata.get('shortcut', 'N/A')}")
                elif metadata.get('type') == 'help_content':
                    print(f"     도움말: {metadata.get('help_text', 'N/A')[:50]}...")
                print()
        
        print("=== 테스트 완료 ===")
        
    except Exception as e:
        print(f"테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

def test_specific_collection_search():
    """특정 컬렉션에서 검색을 테스트합니다."""
    print("\n=== 특정 컬렉션 검색 테스트 ===")
    
    try:
        embedding_db = ChromaDBEmbedding()
        
        # intents 컬렉션에서만 검색
        print("intents 컬렉션에서 검색:")
        results = embedding_db.search_by_collection("파일 삭제", "intents", n_results=3)
        for result in results:
            print(f"  - {result['metadata'].get('intent', 'N/A')} (유사도: {1 - result['distance']:.3f})")
        
        # functions 컬렉션에서만 검색
        print("\nfunctions 컬렉션에서 검색:")
        results = embedding_db.search_by_collection("파일", "functions", n_results=3)
        for result in results:
            print(f"  - {result['metadata'].get('function_name', 'N/A')} (유사도: {1 - result['distance']:.3f})")
        
    except Exception as e:
        print(f"특정 컬렉션 검색 테스트 중 오류 발생: {e}")

if __name__ == "__main__":
    test_embedding()
    test_specific_collection_search() 