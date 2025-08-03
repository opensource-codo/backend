# from langchain_community.chat_models import ChatOpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from typing import Dict
import os
from dotenv import load_dotenv
from db.database import get_function_info as db_get_function_info
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

llm = ChatOpenAI(api_key=api_key)

async def extract_intent(text: str) -> Dict[str, str]:
    prompt = ChatPromptTemplate.from_template(
        "다음 텍스트에서 사용자의 intent를 간단히 추출해줘: {text}"
    )
    chain = prompt | llm
    response = await chain.ainvoke({"text": text})

    content = getattr(response, "content", "").strip()
    return {"intent": content}

async def get_function_info(intent: str) -> Dict[str, str]:
    return db_get_function_info(intent)