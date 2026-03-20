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

from services.ui_guide_service import build_ui_guide

def guide_response_shortcut():
    # 예시 입력
    function_key = "open_taskmgr"
    function_row = {"function_name": "작업 관리자 열기", "shortcut": "Ctrl+Shift+Esc"}

    # 가이드 답변 생성
    response = build_ui_guide(function_key, function_row)

    # 결과 출력
    print("=== 단축키 가이드 응답 ===")
    print(response.get("message_markdown", ""))

def guide_response_no_shortcut():
    # 예시 입력
    function_key = "empty_recycle_bin"
    function_row = {"function_name": "휴지통 비우기"}

    # 가이드 답변 생성
    response = build_ui_guide(function_key, function_row)

    # 결과 출력
    print("=== 단축키X 가이드 응답 ===")
    print(response.get("message_markdown", ""))

if __name__ == "__main__":
    guide_response_shortcut()
    print("\n")
    guide_response_no_shortcut()