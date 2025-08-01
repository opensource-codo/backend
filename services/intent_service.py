# intent_service.py
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from typing import Dict

llm = ChatOpenAI(api_key="OPENAI_API_KEY")

async def extract_intent(text: str) -> Dict[str, str]:
    prompt = ChatPromptTemplate.from_template(
        "다음 텍스트에서 사용자의 intent를 간단히 추출해줘: {text}"
    )
    chain = prompt | llm
    response = chain.invoke({"text": text})

    # 여기서는 단순 예시로 직접 반환. 실제로는 AI 응답 파싱 필요
    return {"intent": response.content.strip()} 