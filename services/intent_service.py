# from langchain_community.chat_models import ChatOpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from typing import Dict, List, Any
import os
from dotenv import load_dotenv
from db.database import get_function_info as db_get_function_info
from services.table_embedding import ChromaDBEmbedding
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

llm = ChatOpenAI(api_key=api_key)

# ChromaDB 임베딩 인스턴스 (싱글톤 패턴)
_embedding_db = None

SIM_THRESHOLD = 0.3

def get_embedding_db() -> ChromaDBEmbedding:
    """ChromaDB 임베딩 인스턴스를 반환합니다."""
    global _embedding_db
    if _embedding_db is None:
        _embedding_db = ChromaDBEmbedding()
    return _embedding_db

async def extract_intent_with_rag(text: str) -> Dict[str, Any]:
    """
    RAG를 사용하여 사용자 입력에서 intent를 추출합니다.
    """
    embedding_db = get_embedding_db()
    
    # ChromaDB에서 유사한 intent 검색
    search_results = embedding_db.search_intent(text, n_results=3)
    
    if not search_results:
        # 검색 결과가 없으면 기존 LLM 방식 사용
        return await extract_intent(text)
    
    # 가장 유사한 결과 선택
    best_match = search_results[0]
    metadata = best_match['metadata']
    similarity = 1 - best_match['distance']
    
    # 유사도가 SIM_THRESHOLD 이상인 경우에만 RAG 결과 사용
    if similarity >= SIM_THRESHOLD:
        return {
            "intent": metadata.get('intent', ''),
            "function_id": metadata.get('function_id', ''),
            "function_name": metadata.get('function_name', ''),
            "shortcut": metadata.get('shortcut', ''),
            "similarity": similarity,
            "method": "rag"
        }
    else:
        # 유사도가 낮으면 LLM 사용
        llm_result = await extract_intent(text)
        return {
            **llm_result,
            "similarity": similarity,
            "method": "llm"
        }

async def extract_intent(text: str) -> Dict[str, str]:
    """기존 LLM 방식으로 intent 추출"""
    prompt = ChatPromptTemplate.from_template(
        "다음 텍스트에서 사용자의 intent를 간단히 추출해줘: {text}"
    )
    chain = prompt | llm
    response = await chain.ainvoke({"text": text})

    content = getattr(response, "content", "").strip()
    return {"intent": content}

async def search_similar_intents(text: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """사용자 입력과 유사한 intsent들을 검색합니다."""
    embedding_db = get_embedding_db()
    return embedding_db.search_intent(text, n_results)