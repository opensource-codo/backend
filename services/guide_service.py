import os
from typing import Optional
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

# 비동기 클라이언트
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_guide_response(message: str, intent: str, shortcut: Optional[str] = None) -> str:
    if shortcut:
        prompt = f"""
        당신은 컴퓨터 기능 도우미입니다.
        사용자가 '{intent}' 기능에 대해 물어봤습니다.
        '{intent}'의 단축키는 {shortcut}입니다.
        이 기능을 어떻게 사용하는지 친절하고 간결하게 안내해 주세요.
        예: '{intent}' 기능을 사용하려면 {shortcut}을 누르세요!
        """
    else:
        prompt = f"""
        당신은 컴퓨터 기능 도우미입니다.
        사용자가 '{intent}' 기능에 대해 물어봤습니다.
        이 기능을 어떻게 사용하는지 윈도우 기준으로 친절하고 간결하게 안내해 주세요.
        예: '{intent}' 기능을 사용하려면 단축키를 누르세요!
        """

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    content = (resp.choices[0].message.content or "").strip()
    return content