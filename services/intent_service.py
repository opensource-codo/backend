# from langchain_community.chat_models import ChatOpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from typing import Dict, List, Any
import os
from dotenv import load_dotenv
from db.database import get_function_info as db_get_function_info
from services.search_chroma import search_intent
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

llm = ChatOpenAI(api_key=api_key)

SIM_THRESHOLD = 0.3

async def extract_intent_with_rag(text: str) -> Dict[str, Any]:
    """
    새로운 Chroma 기반 RAG를 사용하여 사용자 입력에서 intent를 추출합니다.
    """
    try:
        # ChromaDB에서 유사한 intent 검색
        search_results = search_intent(text, top_k=3)
        
        if not search_results or not search_results.get("top"):
            # 검색 결과가 없으면 기존 LLM 방식 사용
            return await extract_intent(text)
        
        # 가장 유사한 결과 선택
        best_match = search_results["top"]
        similarity = best_match.get('score', 0.0)
        
        # 유사도가 SIM_THRESHOLD 이상인 경우에만 RAG 결과 사용
        if similarity >= SIM_THRESHOLD:
            return {
                "intent": best_match.get('intent', ''),
                "function_key": best_match.get('function_key', ''),
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
    except Exception as e:
        # Chroma 검색 실패 시 LLM으로 fallback
        print(f"Chroma search failed: {e}, falling back to LLM")
        return await extract_intent(text)

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
    """사용자 입력과 유사한 intents들을 검색합니다."""
    try:
        search_results = search_intent(text, top_k=n_results)
        candidates = search_results.get("candidates", [])
        
        # 기존 형식과 호환되도록 변환
        formatted_results = []
        for candidate in candidates:
            formatted_results.append({
                "intent": candidate.get("intent", ""),
                "function_key": candidate.get("function_key", ""),
                "score": candidate.get("score", 0.0),
                "similarity": candidate.get("score", 0.0)  # 호환성을 위해
            })
        
        return formatted_results
    except Exception as e:
        print(f"Similar intents search failed: {e}")
        return []