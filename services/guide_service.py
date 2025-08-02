import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_guide_response(message: str, intent: str, shortcut: str = None):
    
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
        이 기능을 어떻게 사용하는지 단계별로 안내해 주세요.
        """

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()