from openai import OpenAI
from dotenv import load_dotenv
import os
import sqlite3
from typing import Dict, Any

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

openai_client = OpenAI(api_key=api_key)

def load_intent_require(intent:str):
    conn = sqlite3.connect('assistant/db')
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""SELECT require_params FROM intents i""")
    require_params = cursor.fetcha()
    conn.close()

def get_params_from_text(text:str, List) -> Dict[str, Any]:
    """사용자 입력 텍스트로부터 존재하는 params 뽑아내기"""
    


def get_text_parameters(intent:str, text:str):


    return