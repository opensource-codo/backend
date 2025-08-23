import json
import os

os.environ["CHROMADB_DEFAULT_EMBEDDING_FUNCTION"] = "none"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import sys
from typing import List, Dict

import pytest
import chromadb
from dotenv import load_dotenv

# Ensure project root is on sys.path so `services` can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from services import build_embed_chroma, search_chroma


def query_search_real(query: str):
    """실제 OpenAI 임베딩을 사용하여 검색 수행"""
    res = search_chroma.search_intent(query, top_k=10)
    print(f"Query: {query}")
    
    status = res.get("status")
    top = res.get("top") or {}
    top_views = top.get("views", []) or []
    views_str = ", ".join(f"{v.get('view')}:{v.get('score'):.3f}" for v in top_views[:3]) if top_views else ""
    
    if top:
        print(
            f"Top => intent: {top.get('intent')} | function_key: {top.get('function_key')} | score: {top.get('score')}" +
            (f" | views: {views_str}" if views_str else "")
        )
    
    print(f"Status: {status}")
    
    # Top 5 candidates 출력
    print("Top 5 Candidates:")
    for i, c in enumerate((res.get("candidates") or [])[:5], 1):
        c_views = c.get("views", []) or []
        c_views_str = ", ".join(f"{v.get('view')}:{v.get('score'):.3f}" for v in c_views[:3]) if c_views else ""
        print(
            f"  {i}. intent: {c.get('intent')} | function_key: {c.get('function_key')} | score: {c.get('score')}" +
            (f" | views: {c_views_str}" if c_views_str else "")
        )
    
    print("")
    return res


@pytest.fixture()
def isolated_chroma(tmp_path, monkeypatch):
    """Redirect Chroma persistence to a tmp directory for both modules."""
    db_dir = tmp_path / "chroma_test_real"
    db_dir.mkdir(parents=True, exist_ok=True)
    original_pc = chromadb.PersistentClient

    def make_client(path=None, *args, **kwargs):
        # Ignore the provided path and force using our isolated tmp directory
        return original_pc(path=str(db_dir))

    # Patch both modules' chroma client factory
    monkeypatch.setattr(build_embed_chroma.chromadb, "PersistentClient", make_client)
    monkeypatch.setattr(search_chroma.chromadb, "PersistentClient", make_client)
    return db_dir


def test_chroma_pipeline_real_openai(isolated_chroma):
    """실제 OpenAI 임베딩을 사용한 Chroma 파이프라인 테스트"""
    # 환경변수 로드
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set. Please set it in .env file")
    
    print(f"Using OpenAI API key: {api_key[:10]}...")
    
    # 1) 실제 OpenAI 임베딩으로 Chroma에 임베딩 생성
    print("Building embeddings with real OpenAI...")
    build_embed_chroma.main()
    
    # 2) 다양한 쿼리로 검색 테스트
    test_queries = [
        "파일 복사해줘",           # file_copy
        "파일 이름 변경하는 방법?",  # rename_file  
        "파일 삭제해줘",           # file_delete
        "스크린 캡처 어떻게 해?",   # screen_capture
        "제어판 열어줘",           # open_control_panel
        "파일 붙여넣기 어떻게 해?", # file_paste
        "파일 잘라내기 실행해줘",   # file_cut
        "휴지통 비우기",           # empty_recycle_bin
        "네트워크 재설정",         # reset_network
        "디스크 정리",             # defrag_disk
    ]
    
    print(f"Testing {len(test_queries)} queries with real embeddings...")
    print("=" * 80)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n--- Query {i}/{len(test_queries)} ---")
        res = query_search_real(query)
        
        # 기본 검증
        assert res["query"] == query
        assert isinstance(res.get("candidates"), list)
        assert res.get("top") is not None
        assert "function_key" in res["top"]
        assert res.get("status") in {"ok", "low_confidence"}
        
        # 점수 검증 (실제 임베딩이므로 더 높은 점수 기대)
        if res.get("top"):
            score = res["top"].get("score", 0)
            print(f"Score validation: {score:.3f}")
            # 실제 임베딩이므로 더 높은 점수 기대 (임계값 조정 가능)
            assert score > 0.1, f"Score too low: {score}"
    
    print("\n" + "=" * 80)
    print("All queries completed successfully with real OpenAI embeddings!")


def test_specific_query_accuracy(isolated_chroma):
    """특정 쿼리에 대한 정확도 테스트"""
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    
    # 임베딩 생성
    build_embed_chroma.main()
    
    # 파일 복사 관련 쿼리들
    copy_queries = [
        "파일 복사해줘",
        "파일을 복사하고 싶어",
        "복사 기능 사용법",
        "copy file",
        "파일 카피"
    ]
    
    print("\n=== 파일 복사 관련 쿼리 정확도 테스트 ===")
    
    for query in copy_queries:
        res = query_search_real(query)
        top = res.get("top", {})
        
        # 파일 복사 관련 function_key가 상위에 있는지 확인
        function_key = top.get("function_key", "")
        score = top.get("score", 0)
        
        print(f"Query: '{query}'")
        print(f"  Top result: {function_key} (score: {score:.3f})")
        
        # file_copy가 상위 3개 안에 있는지 확인
        candidates = res.get("candidates", [])
        copy_found = any(c.get("function_key") == "file_copy" for c in candidates[:3])
        
        if copy_found:
            print(f"  ✅ file_copy found in top 3")
        else:
            print(f"  ❌ file_copy NOT in top 3")
            print(f"  Top 3: {[c.get('function_key') for c in candidates[:3]]}")
        
        print()


if __name__ == "__main__":
    # 직접 실행 시
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set in .env file")
        print("Please create .env file with: OPENAI_API_KEY=your_api_key_here")
        sys.exit(1)
    
    print("Running Chroma pipeline test with real OpenAI embeddings...")
    pytest.main([__file__, "-s", "-v"])
