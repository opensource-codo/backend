# validator_service.py
from typing import Dict, Any, List, Optional, Tuple
import sqlite3
import re
import os

class ValidatorService:
    def __init__(self, db_path: str = "assistant.db"):
        self.db_path = db_path
    
    def get_db_connection(self):
        """SQLite 데이터베이스 연결을 반환합니다."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_function_params(self, function_key: str) -> Dict[str, Any]:
        """DB에서 function의 파라미터 정보를 가져옵니다."""
        conn = self.get_db_connection()
        try:
            # functions 테이블에서 function_key로 검색
            cursor = conn.execute("""
                SELECT id, function_key, function_name, script_path, shortcut, script_command
                FROM functions 
                WHERE function_key = ?
            """, (function_key,))
            
            function_row = cursor.fetchone()
            if not function_row:
                return {"required": [], "optional": [], "danger": False}
            
            # function_key에 따른 기본 파라미터 스키마
            # 실제로는 별도 테이블(intent_params)을 만들어서 관리하는 것이 좋습니다
            default_schemas = self._get_default_param_schemas()
            return default_schemas.get(function_key, {"required": [], "optional": [], "danger": False})
            
        finally:
            conn.close()
    
    def get_intent_params(self, intent: str) -> Dict[str, Any]:
        """DB에서 intent의 파라미터 정보를 가져옵니다."""
        conn = self.get_db_connection()
        try:
            # intents 테이블에서 intent로 검색하고 function_id로 연결
            cursor = conn.execute("""
                SELECT i.intent, f.function_key
                FROM intents i
                LEFT JOIN functions f ON i.function_id = f.id
                WHERE i.intent = ?
            """, (intent,))
            
            intent_row = cursor.fetchone()
            if not intent_row:
                return {"required": [], "optional": [], "danger": False}
            
            function_key = intent_row['function_key']
            if function_key:
                return self.get_function_params(function_key)
            else:
                return {"required": [], "optional": [], "danger": False}
                
        finally:
            conn.close()
    
    def _get_default_param_schemas(self) -> Dict[str, Dict[str, Any]]:
        """기본 파라미터 스키마를 반환합니다."""
        return {
            "copy_file": {
                "required": [
                    {"name": "src_path", "type": "path", "description": "복사할 파일 경로"},
                    {"name": "dst_path", "type": "path", "description": "복사할 대상 경로"}
                ],
                "optional": [],
                "danger": False
            },
            "delete_file": {
                "required": [
                    {"name": "target_path", "type": "path", "description": "삭제할 파일 경로"}
                ],
                "optional": [
                    {"name": "force", "type": "bool", "default": False, "description": "강제 삭제 여부"}
                ],
                "danger": True
            },
            "rename_file": {
                "required": [
                    {"name": "old_path", "type": "path", "description": "기존 파일 경로"},
                    {"name": "new_path", "type": "path", "description": "새 파일 경로"}
                ],
                "optional": [],
                "danger": False
            },
            "screenshot": {
                "required": [],
                "optional": [
                    {"name": "region", "type": "enum", "choices": ["full", "active_window", "custom"], "default": "full", "description": "캡처 영역"},
                    {"name": "save_path", "type": "path", "description": "저장 경로"}
                ],
                "danger": False
            },
            "block_remote_access": {
                "required": [
                    {"name": "enabled", "type": "bool", "description": "원격 접속 차단 여부"}
                ],
                "optional": [],
                "danger": True
            }
        }
    
    def validate(self, intent: str, parameters: Dict[str, Any], method: str = "GUIDE", text: str = "") -> Dict[str, Any]:
        """
        intent와 파라미터를 검증합니다.
        
        Args:
            intent: 검증할 intent
            parameters: 검증할 파라미터
            method: 실행 방법 (GUIDE, EXECUTION)
            text: 원본 텍스트 (파라미터 추출용)
        
        Returns:
            {
                "valid": bool,
                "missing_params": List[str],
                "normalized_params": Dict[str, Any],
                "errors": List[str],
                "requires_confirmation": bool,
                "message": str
            }
        """
        method = (method or "GUIDE").upper()
        
        # GUIDE는 파라미터 검증 불필요
        if method == "GUIDE":
            return {
                "valid": True,
                "missing_params": [],
                "normalized_params": {},
                "errors": [],
                "requires_confirmation": False,
                "message": "가이드 모드: 파라미터 검증이 필요하지 않습니다."
            }
        
        # DB에서 파라미터 스키마 가져오기
        schema = self.get_intent_params(intent)
        
        # 텍스트에서 파라미터 추출 시도
        guessed_params = self._extract_params_from_text(intent, text)
        
        # 추출된 파라미터와 전달된 파라미터 병합
        merged_params = {**guessed_params, **(parameters or {})}
        
        # 스키마에 따른 검증 및 정규화
        normalized, missing, errors = self._apply_schema(merged_params, schema)
        
        # # SIMULATION: 필수 파라미터 누락 허용
        # if method == "SIMULATION":
        #     valid = True
        #     msg = "시뮬레이션 모드: 일부 파라미터가 누락되었지만 실행 가능합니다." if missing else "시뮬레이션 모드: 모든 파라미터가 준비되었습니다."
        #     return {
        #         "valid": valid,
        #         "missing_params": missing,
        #         "normalized_params": normalized,
        #         "errors": errors,
        #         "requires_confirmation": bool(schema.get("danger", False)),
        #         "message": msg
        #     }
        
        # EXECUTION: 모든 필수 파라미터가 필요
        if method == "EXECUTION":
            if missing or errors:
                parts = []
                if missing:
                    parts.append(f"누락: {', '.join(missing)}")
                if errors:
                    parts.append(f"오류: {', '.join(errors)}")
                return {
                    "valid": False,
                    "missing_params": missing,
                    "normalized_params": normalized,
                    "errors": errors,
                    "requires_confirmation": False,
                    "message": "실행 모드: " + "; ".join(parts)
                }

            return {
                "valid": True,
                "missing_params": [],
                "normalized_params": normalized,
                "errors": [],
                "requires_confirmation": bool(schema.get("danger", False)),
                "message": "실행 모드: 모든 파라미터가 준비되었습니다."
            }
        
        # 알 수 없는 method
        return {
            "valid": False,
            "missing_params": [],
            "normalized_params": {},
            "errors": [f"지원하지 않는 method: {method}"],
            "requires_confirmation": False,
            "message": "잘못된 실행 방법입니다."
        }
    
    def _extract_params_from_text(self, intent: str, text: str) -> Dict[str, Any]:
        """텍스트에서 파라미터를 추출합니다."""
        if not text:
            return {}
        
        # function_key 찾기
        function_key = self._get_function_key_from_intent(intent)
        if not function_key:
            return {}
        
        extracted = {}
        
        if function_key == "copy_file":
            # 파일 경로 2개 찾기
            paths = re.findall(r'[A-Za-z]:\\[^:*?"<>|]+', text)
            if len(paths) >= 2:
                extracted["src_path"] = paths[0]
                extracted["dst_path"] = paths[1]
        
        elif function_key == "delete_file":
            # 파일 경로 1개 찾기
            paths = re.findall(r'[A-Za-z]:\\[^:*?"<>|]+', text)
            if paths:
                extracted["target_path"] = paths[0]
        
        elif function_key == "rename_file":
            # 파일 경로 2개 찾기
            paths = re.findall(r'[A-Za-z]:\\[^:*?"<>|]+', text)
            if len(paths) >= 2:
                extracted["old_path"] = paths[0]
                extracted["new_path"] = paths[1]
        
        elif function_key == "block_remote_access":
            # 차단/해제 키워드 찾기
            text_lower = text.lower()
            if any(keyword in text_lower for keyword in ["차단", "block", "켜", "enable", "on"]):
                extracted["enabled"] = True
            elif any(keyword in text_lower for keyword in ["해제", "off", "disable", "끄"]):
                extracted["enabled"] = False
        
        return extracted
    
    def _get_function_key_from_intent(self, intent: str) -> Optional[str]:
        """intent에서 function_key를 가져옵니다."""
        conn = self.get_db_connection()
        try:
            cursor = conn.execute("""
                SELECT f.function_key
                FROM intents i
                LEFT JOIN functions f ON i.function_id = f.id
                WHERE i.intent = ?
            """, (intent,))
            
            row = cursor.fetchone()
            return row['function_key'] if row else None
            
        finally:
            conn.close()
    
    def _apply_schema(self, parameters: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str]]:
        """스키마에 따라 파라미터를 정규화하고 검증합니다."""
        params_out = {}
        missing = []
        errors = []
        
        # 필수 파라미터 검증
        for spec in schema.get("required", []):
            name = spec["name"]
            param_type = spec.get("type", "str")
            value = parameters.get(name)
            
            if value is None:
                missing.append(name)
                continue
            
            # 타입 변환 및 검증
            success, converted = self._validate_and_convert(name, value, param_type, spec)
            if not success:
                errors.append(f"{name}: 유효하지 않은 값")
            else:
                params_out[name] = converted
        
        # 선택적 파라미터 처리
        for spec in schema.get("optional", []):
            name = spec["name"]
            param_type = spec.get("type", "str")
            
            if name in parameters and parameters[name] is not None:
                success, converted = self._validate_and_convert(name, parameters[name], param_type, spec)
                if not success:
                    errors.append(f"{name}: 유효하지 않은 값")
                else:
                    params_out[name] = converted
            else:
                # 기본값 설정
                if "default" in spec:
                    params_out[name] = spec["default"]
            # cross-field checks
            
        fk = None
        # 가능하면 intent→function_key를 가져와서 판단
        # fk = self._get_function_key_from_intent(intent)  # intent 인자를 넘겨받도록 시그니처 늘릴 수도
        # 여기선 parameters에 힌트를 둔다고 가정
        if "src_path" in params_out and "dst_path" in params_out:
            if params_out["src_path"].lower() == params_out["dst_path"].lower():
                errors.append("src_path와 dst_path가 동일합니다.")
        if "old_path" in params_out and "new_path" in params_out:
            if params_out["old_path"].lower() == params_out["new_path"].lower():
                errors.append("old_path와 new_path가 동일합니다.")
        return params_out, missing, errors
    
    def _validate_and_convert(self, name: str, value: Any, param_type: str, spec: Dict[str, Any]) -> Tuple[bool, Any]:
        """파라미터 값을 검증하고 변환합니다."""
        if param_type == "bool":
            converted = self._coerce_bool(value)
            return (converted is not None, converted)
        
        elif param_type == "path":
            converted = self._coerce_path(value)
            return (converted is not None, converted)
        
        elif param_type == "enum":
            choices = spec.get("choices", [])
            converted = self._coerce_enum(value, choices)
            return (converted is not None, converted)
        
        # 기본 문자열
        if value is None:
            return (False, None)
        
        return (True, str(value))
    
    def _coerce_bool(self, value: Any) -> Optional[bool]:
        """값을 boolean으로 변환합니다."""
        if isinstance(value, bool):
            return value
        
        if isinstance(value, str):
            s = value.strip().lower()
            if s in {"true", "1", "yes", "y", "켜", "on"}:
                return True
            if s in {"false", "0", "no", "n", "끄", "off"}:
                return False
        
        if isinstance(value, (int, float)):
            return bool(value)
        
        return None
    
    def _coerce_path(self, value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        s = value.strip().strip('"').strip("'")      # 따옴표 제거
        s = s.replace('/', '\\')                     # 슬래시 정규화
        try:
            norm = os.path.normpath(s)
        except Exception:
            return None
        # UNC(\\server\share) 또는 드라이브 경로 허용
        if re.match(r'^(\\\\[^\\/:*?"<>|]+\\[^:*?"<>|]+|[A-Za-z]:\\)', norm):
            # 금지문자 포함 여부 최종 체크
            if re.search(r'[:*?"<>|]', norm.split(':', 1)[-1]):
                return None
            return norm
        return None
    
    def _coerce_enum(self, value: Any, choices: List[str]) -> Optional[str]:
        """값을 enum으로 변환합니다."""
        if isinstance(value, str):
            s = value.strip().lower()
            for choice in choices:
                if s == choice.lower():
                    return choice
        
        return None

# 전역 인스턴스 생성
validator_service = ValidatorService()

# 기존 코드와의 호환성을 위한 함수
def validate(intent: str, parameters: Dict[str, Any], method: str = "GUIDE", text: str = "") -> Dict[str, Any]:
    """
    기존 코드와의 호환성을 위한 함수입니다.
    validator_service.validate()를 호출합니다.
    """
    return validator_service.validate(intent, parameters, method, text) 