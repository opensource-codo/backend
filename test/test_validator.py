#!/usr/bin/env python3
"""
validator_service 테스트 스크립트
"""
import sys
import os

# 현재 파일의 디렉토리에서 상위 디렉토리로 이동하여 backend 폴더를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from services.validator_service import ValidatorService

def test_validator():
    """validator_service를 테스트합니다."""
    print("=== ValidatorService 테스트 ===")
    
    validator = ValidatorService()
    
    # 1. 파일 복사 테스트
    print("\n1. 파일 복사 테스트:")
    result = validator.validate(
        intent="파일 복사",
        parameters={},
        method="EXECUTION",
        text="C:\\Users\\test.txt를 C:\\backup\\test.txt로 복사해줘"
    )
    print(f"   결과: {result}")
    
    # 2. 파일 삭제 테스트
    print("\n2. 파일 삭제 테스트:")
    result = validator.validate(
        intent="파일 삭제",
        parameters={},
        method="EXECUTION",
        text="C:\\temp\\old.txt 파일을 삭제해줘"
    )
    print(f"   결과: {result}")
    
    # 3. GUIDE 모드 테스트
    print("\n3. GUIDE 모드 테스트:")
    result = validator.validate(
        intent="파일 복사",
        parameters={},
        method="GUIDE",
        text="파일을 복사하는 방법을 알려줘"
    )
    print(f"   결과: {result}")
    
    # 4. 파라미터가 있는 경우 테스트
    print("\n4. 파라미터가 있는 경우 테스트:")
    result = validator.validate(
        intent="파일 복사",
        parameters={"src_path": "C:\\source.txt", "dst_path": "C:\\dest.txt"},
        method="EXECUTION",
        text="파일을 복사해줘"
    )
    print(f"   결과: {result}")
    
    # 5. function_key 조회 테스트
    print("\n5. function_key 조회 테스트:")
    function_key = validator._get_function_key_from_intent("파일 복사")
    print(f"   '파일 복사'의 function_key: {function_key}")
    
    # 6. 파라미터 스키마 조회 테스트
    print("\n6. 파라미터 스키마 조회 테스트:")
    schema = validator.get_function_params("파일 복사")
    print(f"   '파일 복사'의 스키마: {schema}")

if __name__ == "__main__":
    test_validator()
