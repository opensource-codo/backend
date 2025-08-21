from typing import Dict, Any, List, Optional, Tuple
import sqlite3
import re
import os
import json

# ───────────────────────────────────────────────
# 별칭 맵 (DB에 매핑이 없을 때 폴백)
# ───────────────────────────────────────────────
_ALIAS_MAP = {
    # 폴더/파일 작업
    "create_folder": "create_folder",
    "mkdir": "create_folder",
    "폴더 생성": "create_folder",
    "디렉터리 생성": "create_folder",

    "copy_file": "copy_file",
    "파일 복사": "copy_file",

    "move_file": "move_file",
    "파일 이동": "move_file",

    "rename_file": "rename_file",
    "파일 이름 변경": "rename_file",

    # 위험 작업
    "empty_recycle_bin": "empty_recycle_bin",
    "휴지통 비우기": "empty_recycle_bin",
    "shutdown": "shutdown",

    # 추가: 제어판 열기
    "open_control_panel": "open_control_panel",
    "제어판 열기": "open_control_panel",
    "control panel": "open_control_panel",
    "control": "open_control_panel",
}


class ValidatorService:
    def __init__(self, db_path: str = "assistant.db"):
        self.db_path = db_path

    # ───────────────────────────────────────────────
    # DB 유틸
    # ───────────────────────────────────────────────
    def get_db_connection(self):
        """SQLite 데이터베이스 연결을 반환합니다."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, name: str) -> bool:
        try:
            conn = self.get_db_connection()
            cur = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            )
            ok = cur.fetchone() is not None
            conn.close()
            return ok
        except Exception:
            return False

    # ───────────────────────────────────────────────
    # 스키마 로딩 (DB 우선 → 하드코딩 폴백)
    # ───────────────────────────────────────────────
    def _get_schema_from_db(self, function_key: str) -> Dict[str, Any]:
        """
        intent_params에서 function_key의 파라미터 스키마를 읽는다.
        없으면 {} 반환.
        """
        if not function_key or not self._table_exists("intent_params"):
            return {}

        conn = self.get_db_connection()
        try:
            # TODO : required DB 구조 보고 수정 필요
            cur = conn.execute(
                """
                SELECT name, type, required, default_json, choices_json, description
                FROM intent_params
                WHERE function_key = ?
                ORDER BY required DESC, name ASC
                """,
                (function_key,),
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return {}

        required, optional = [], []
        for r in rows:
            spec: Dict[str, Any] = {
                "name": r["name"],
                "type": r["type"] or "str",
                "description": r["description"] or "",
            }
            if r["default_json"]:
                try:
                    spec["default"] = json.loads(r["default_json"])
                except Exception:
                    spec["default"] = r["default_json"]
            if r["choices_json"]:
                try:
                    spec["choices"] = json.loads(r["choices_json"])
                except Exception:
                    spec["choices"] = [
                        s.strip() for s in str(r["choices_json"]).split(",") if s.strip()
                    ]

            if int(r["required"] or 0):
                required.append(spec)
            else:
                optional.append(spec)

        danger = self._get_function_danger(function_key)
        return {"required": required, "optional": optional, "danger": bool(danger)}

    def _get_function_danger(self, function_key: str) -> int:
        """
        functions.danger (0/1) 값을 읽는다. 컬럼이 없거나 NULL이면 0.
        """
        conn = self.get_db_connection()
        try:
            cur = conn.execute(
                "SELECT COALESCE(danger, 0) AS danger FROM functions WHERE function_key = ?",
                (function_key,),
            )
            row = cur.fetchone()
            return int(row["danger"]) if row and row["danger"] is not None else 0
        except Exception:
            return 0
        finally:
            conn.close()

    def get_function_params(self, function_key: str) -> Dict[str, Any]:
        """
        function_key 기준 스키마 조회. DB(intent_params) 우선, 없으면 하드코딩 폴백.
        """
        # 1) DB
        schema = self._get_schema_from_db(function_key)
        if schema:
            return schema
        # 2) fallback
        default_schemas = self._get_default_param_schemas()
        schema = default_schemas.get(
            function_key, {"required": [], "optional": [], "danger": False}
        )
        return schema

    def get_intent_params(self, intent: str) -> Dict[str, Any]:
        """
        intent 기준 스키마 조회.
        intent -> functions.function_key 조인 후, get_function_params로 조회.
        매핑이 없으면 별칭 폴백 → 그래도 없으면 not_configured=True.
        """
        conn = self.get_db_connection()
        try:
            cursor = conn.execute(
                """
                SELECT f.function_key AS fk
                FROM intents i
                LEFT JOIN functions f ON i.function_id = f.id   -- ✅ 올바른 조인
                WHERE i.intent = ?
                """,
                (intent,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        if row and row["fk"]:
            return self.get_function_params(row["fk"])

        # DB에 없으면 별칭 폴백
        fk = self._alias(intent)
        if fk:
            return self.get_function_params(fk)

        # 의도는 있지만 기능 매핑이 안 된 구성 이슈
        return {"required": [], "optional": [], "danger": False, "not_configured": True}

    def _alias(self, intent: str) -> Optional[str]:
        if not intent:
            return None
        s = intent.strip().lower()
        if s in _ALIAS_MAP:
            return _ALIAS_MAP[s]
        for k, v in _ALIAS_MAP.items():
            if k in s:
                return v
        return None

    def _get_default_param_schemas(self) -> Dict[str, Dict[str, Any]]:
        """하드코딩 기본 스키마(폴백용)."""
        return {
            # 기존 제공 스키마
            "copy_file": {
                "required": [
                    {"name": "src_path", "type": "path", "description": "복사할 파일 경로"},
                    {"name": "dst_path", "type": "path", "description": "복사할 대상 경로"},
                ],
                "optional": [],
                "danger": False,
            },
            "delete_file": {
                "required": [
                    {"name": "target_path", "type": "path", "description": "삭제할 파일 경로"}
                ],
                "optional": [
                    {
                        "name": "force",
                        "type": "bool",
                        "default": False,
                        "description": "강제 삭제 여부",
                    }
                ],
                "danger": True,
            },
            "rename_file": {
                "required": [
                    {"name": "old_path", "type": "path", "description": "기존 파일 경로"},
                    {"name": "new_path", "type": "path", "description": "새 파일 경로"},
                ],
                "optional": [],
                "danger": False,
            },
            "screenshot": {
                "required": [],
                "optional": [
                    {
                        "name": "region",
                        "type": "enum",
                        "choices": ["full", "active_window", "custom"],
                        "default": "full",
                        "description": "캡처 영역",
                    },
                    {"name": "save_path", "type": "path", "description": "저장 경로"},
                ],
                "danger": False,
            },
            "block_remote_access": {
                "required": [
                    {"name": "enabled", "type": "bool", "description": "원격 접속 차단 여부"}
                ],
                "optional": [],
                "danger": True,
            },

            # 폴백 추가 스키마
            "create_folder": {
                "required": [
                    {"name": "path", "type": "path", "description": "부모 경로"},
                    {"name": "name", "type": "str",  "description": "새 폴더 이름"},
                ],
                "optional": [],
                "danger": False,
            },
            "move_file": {
                "required": [
                    {"name": "src_path", "type": "path", "description": "원본 경로"},
                    {"name": "dst_path", "type": "path", "description": "대상 경로"},
                ],
                "optional": [],
                "danger": False,
            },
            "empty_recycle_bin": {
                "required": [],
                "optional": [],
                "danger": True,  # 확인 필요
            },
            "shutdown": {
                "required": [],
                "optional": [],
                "danger": True,  # 확인 필요
            },

            # 추가: 제어판 열기
            "open_control_panel": {
                "required": [],
                "optional": [],
                "danger": False,
            },
        }

    # ───────────────────────────────────────────────
    # 검증 메인
    # ───────────────────────────────────────────────
    def validate(
        self,
        intent: str,
        parameters: Dict[str, Any],
        text: str = "",
        method: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        intent와 파라미터를 검증합니다.
        method가 주어지지 않으면 EXECUTION으로 간주합니다.
        """
        method_upper = (method or "EXECUTION").upper()

        # 스키마 로딩
        schema = self.get_intent_params(intent)
        if schema.get("not_configured"):
            return {
                "valid": False,
                "missing_params": [],
                "normalized_params": {},
                "errors": ["해당 intent가 function에 매핑되지 않았습니다."],
                "requires_confirmation": False,
                "message": "구성되지 않은 의도입니다. 관리자에게 기능 매핑을 요청하세요.",
            }

        # 텍스트에서 파라미터 추정
        guessed_params = self._extract_params_from_text(intent, text)

        # 전달 파라미터와 병합 (전달값이 우선)
        merged_params = {**guessed_params, **(parameters or {})}

        # 스키마 검증/정규화
        normalized, missing, errors = self._apply_schema(merged_params, schema)

        if method_upper == "EXECUTION":
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
                    "message": "실행 모드: " + "; ".join(parts),
                }

            # 위험도 판단: 스키마 danger OR 텍스트 패턴
            danger_flag = bool(schema.get("danger", False))
            text_lc = f"{intent} {text}".lower()
            if re.search(r"\bshutdown\b", text_lc) or \
               re.search(r"\bformat(-|_)?volume\b", text_lc) or \
               re.search(r"\brm\s+-rf\b", text_lc) or \
               re.search(r"clear(-|_)?recyclebin", text_lc):
                danger_flag = True

            return {
                "valid": True,
                "missing_params": [],
                "normalized_params": normalized,
                "errors": [],
                "requires_confirmation": danger_flag,
                "message": "실행 모드: 모든 파라미터가 준비되었습니다.",
            }

        if method_upper == "GUIDE":
            # GUIDE 모드는 검증이 핵심이 아니므로 OK로 간주(실행은 아님)
            return {
                "valid": True,
                "missing_params": [],
                "normalized_params": {},
                "errors": [],
                "requires_confirmation": False,
                "message": "가이드 모드: 검증을 수행하지 않습니다.",
            }

        # 알 수 없는 method
        return {
            "valid": False,
            "missing_params": [],
            "normalized_params": {},
            "errors": [f"지원하지 않는 method: {method_upper}"],
            "requires_confirmation": False,
            "message": "잘못된 실행 방법입니다.",
        }

    # ───────────────────────────────────────────────
    # 텍스트 → 파라미터 추정
    # ───────────────────────────────────────────────
    def _extract_params_from_text(self, intent: str, text: str) -> Dict[str, Any]:
        """텍스트에서 파라미터를 추출(추정)합니다. (검증/정규화는 _apply_schema에서)"""
        if not text:
            return {}

        # intent → function_key (DB 우선, 없으면 별칭 폴백)
        function_key = self._get_function_key_from_intent(intent)
        if not function_key:
            return {}

        # Windows 경로 캡처(따옴표 포함 케이스 대비)
        # 예: "C:\a b\c.txt" D:\d
        path_pattern = r'(?:"([A-Za-z]:\\[^:*?"<>|]+)"|([A-Za-z]:\\[^:*?"<>|]+))'
        paths = []
        for m in re.finditer(path_pattern, text):
            p = m.group(1) or m.group(2)
            if p:
                paths.append(p)

        extracted: Dict[str, Any] = {}

        if function_key == "copy_file":
            if len(paths) >= 2:
                extracted["src_path"] = paths[0]
                extracted["dst_path"] = paths[1]

        elif function_key == "delete_file":
            if paths:
                extracted["target_path"] = paths[0]

        elif function_key == "rename_file":
            if len(paths) >= 2:
                extracted["old_path"] = paths[0]
                extracted["new_path"] = paths[1]

        elif function_key == "move_file":
            if len(paths) >= 2:
                extracted["src_path"] = paths[0]
                extracted["dst_path"] = paths[1]

        elif function_key == "create_folder":
            # "C:\Temp\Logs"만 주어졌을 때 path/name 자동 분리
            if paths:
                parent, leaf = os.path.split(paths[0])
                if parent and leaf:
                    extracted["path"] = parent
                    extracted["name"] = leaf

        elif function_key == "block_remote_access":
            text_lower = text.lower()
            if any(k in text_lower for k in ["차단", "block", "켜", "enable", "on"]):
                extracted["enabled"] = True
            elif any(k in text_lower for k in ["해제", "off", "disable", "끄"]):
                extracted["enabled"] = False

        # open_control_panel은 파라미터 없음
        return extracted

    def _get_function_key_from_intent(self, intent: str) -> Optional[str]:
        """intent에서 function_key를 가져옵니다. DB 매핑 우선, 없으면 별칭 폴백."""
        conn = self.get_db_connection()
        try:
            cursor = conn.execute(
                """
                SELECT f.function_key
                FROM intents i
                LEFT JOIN functions f ON i.function_id = f.id
                WHERE i.intent = ?
                """,
                (intent,),
            )
            row = cursor.fetchone()
            if row and row["function_key"]:
                return row["function_key"]
        finally:
            conn.close()
        return self._alias(intent)

    # ───────────────────────────────────────────────
    # 스키마 적용(정규화/검증)
    # ───────────────────────────────────────────────
    def _apply_schema(
        self, parameters: Dict[str, Any], schema: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[str], List[str]]:
        """스키마에 따라 파라미터를 정규화하고 검증합니다."""
        params_out: Dict[str, Any] = {}
        missing: List[str] = []
        errors: List[str] = []

        # 필수 파라미터 검증
        for spec in schema.get("required", []):
            name = spec["name"]
            ptype = spec.get("type", "str")
            value = parameters.get(name)

            if value is None:
                missing.append(name)
                continue

            ok, converted = self._validate_and_convert(name, value, ptype, spec)
            if not ok:
                errors.append(f"{name}: 유효하지 않은 값")
            else:
                params_out[name] = converted

        # 선택적 파라미터 처리
        for spec in schema.get("optional", []):
            name = spec["name"]
            ptype = spec.get("type", "str")
            if name in parameters and parameters[name] is not None:
                ok, converted = self._validate_and_convert(name, parameters[name], ptype, spec)
                if not ok:
                    errors.append(f"{name}: 유효하지 않은 값")
                else:
                    params_out[name] = converted
            else:
                if "default" in spec:
                    params_out[name] = spec["default"]

        # 교차 필드 체크
        if "src_path" in params_out and "dst_path" in params_out:
            if str(params_out["src_path"]).lower() == str(params_out["dst_path"]).lower():
                errors.append("src_path와 dst_path가 동일합니다.")
        if "old_path" in params_out and "new_path" in params_out:
            if str(params_out["old_path"]).lower() == str(params_out["new_path"]).lower():
                errors.append("old_path와 new_path가 동일합니다.")

        return params_out, missing, errors

    # ───────────────────────────────────────────────
    # 타입별 변환기
    # ───────────────────────────────────────────────
    def _validate_and_convert(
        self, name: str, value: Any, param_type: str, spec: Dict[str, Any]
    ) -> Tuple[bool, Any]:
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
        """값을 Windows 경로로 정규화/검증."""
        if not isinstance(value, str):
            return None
        s = value.strip().strip('"').strip("'")  # 따옴표 제거
        s = s.replace("/", "\\")  # 슬래시 정규화
        try:
            norm = os.path.normpath(s)
        except Exception:
            return None
        # UNC(\\server\share) 또는 드라이브 경로 허용
        if re.match(r"^(\\\\[^\\/:*?\"<>|]+\\[^:*?\"<>|]+|[A-Za-z]:\\)", norm):
            # 금지문자 포함 여부 최종 체크 (드라이브 문자 뒤만 검사)
            if re.search(r'[:*?"<>|]', norm.split(":", 1)[-1]):
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

# 공개 래퍼: 텍스트에서 파라미터만 대략 추정 (검증/정규화는 validate에서 처리)
def validate_text_parameters(intent: str, text: str) -> Dict[str, Any]:
    if not intent or not text:
        return {}
    try:
        return validator_service._extract_params_from_text(intent, text)
    except Exception:
        return {}

# 기존 코드와의 호환성을 위한 함수
def validate(
    intent: str,
    parameters: Dict[str, Any],
    text: str = "",
    method: Optional[str] = None,
) -> Dict[str, Any]:
    """
    기존 코드와의 호환성을 위한 함수입니다.
    validator_service.validate()를 호출합니다.
    """
    return validator_service.validate(intent, parameters, text, method)
