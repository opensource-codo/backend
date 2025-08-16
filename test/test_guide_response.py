#!/usr/bin/env python3
"""
GUIDE 응답 테스트 스크립트
"""
import sys
import os

# 현재 파일의 디렉토리에서 상위 디렉토리로 이동하여 backend 폴더를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

import asyncio
from services.guide_service import generate_guide_response 
import services.guide_service as guide_service
from services.table_embedding import ChromaDBEmbedding, create_embedding_instance, search_intent_from_query

async def guide_response_shortcut():
    # 예시 입력
    intent = "붙여넣기"
    shortcut = "Ctrl+V"
    message = "붙여넣기 하는 방법 알려줘"

    # 가이드 답변 생성
    response = await generate_guide_response(message, intent, shortcut)

    # 결과 출력
    print("=== 단축키 가이드 응답 ===")
    print(response)
    
async def guide_response_no_shortcut():
    # 예시 입력
    intent = "붙여넣기"
    message = "붙여넣기 하는 방법 알려줘"

    # 가이드 답변 생성
    response = await generate_guide_response(message, intent)

    # 결과 출력
    print("=== 단축키X 가이드 응답 ===")
    print(response)

if __name__ == "__main__":
    asyncio.run(guide_response_shortcut())
    print("\n")
    asyncio.run(guide_response_no_shortcut())