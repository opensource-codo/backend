# services/param_extractor.py
from __future__ import annotations
from typing import Dict, Any
import os
import json
import re
from openai import OpenAI

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _prop_for_type(t: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    desc = (spec.get("description") or "").strip()
    if t == "bool":
        return {"type": "boolean", "description": desc}
    if t == "enum":
        choices = spec.get("choices") or []
        # enum이 비어 있으면 안전하게 string로 폴백
        return {"type": "string", "enum": choices} if choices else {"type": "string"}
    # path/str → string
    return {"type": "string", "description": desc}

def _build_tool_schema(intent: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chat Completions tools 파라미터 JSON 스키마 생성.
    *추출 단계*에서는 누락 허용을 위해 모든 필드를 optional로 둔다.
    (필수 필터링은 validator에서 수행)
    """
    props: Dict[str, Any] = {}
    for spec in (schema.get("required") or []):
        props[spec["name"]] = _prop_for_type(spec.get("type", "str"), spec)
    for spec in (schema.get("optional") or []):
        props[spec["name"]] = _prop_for_type(spec.get("type", "str"), spec)

    return {
        "type": "function",
        "function": {
            "name": "set_params",
            "description": f"Extract parameters for intent '{intent}'. Return only fields present in the schema.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": props,
                # 추출 단계에서는 required 비움 (필수 여부는 검증 단계에서 판단)
                "required": []
            }
        }
    }

_SYS_PROMPT = (
    "You are a strict parameter extractor. "
    "Given the user's Korean text and the intent, extract only parameters that are explicitly present. "
    "Do not hallucinate or invent values. "
    "Return values exactly as found (e.g., Windows paths keep slashes/backslashes and quotes removed). "
    "If a value is not present, omit that field. "
    "For booleans, map Korean synonyms: '켜/ON/enable' → true, '끄/OFF/disable' → false."
)

def extract_params_llm(intent: str, text: str, schema: Dict[str, Any], model: str = "gpt-4o-mini") -> Dict[str, Any]:
    """
    OpenAI Chat Completions + function calling 로 파라미터 추출.
    - schema: validator_service.get_intent_params(intent) 결과 (required/optional/danger(caution) 포함)
    - 반환: 스키마 키만 포함한 dict
    """
    if not (intent and text and schema):
        return {}

    tool = _build_tool_schema(intent, schema)

    messages = [
        {"role": "system", "content": _SYS_PROMPT},
        {
            "role": "user",
            "content": (
                f"[Intent]: {intent}\n"
                "아래 사용자 입력에서 의도에 맞는 파라미터만 뽑아주세요.\n"
                "값이 없으면 해당 필드는 아예 넣지 마세요.\n\n"
                f"[User Text]: {text}"
            ),
        },
    ]

    try:
        resp = _client.chat.completions.create(
            model=model,
            temperature=0,
            messages=messages,
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": "set_params"}},
        )
        choice = resp.choices[0]
        tool_calls = getattr(choice.message, "tool_calls", None) or []
        if not tool_calls:
            return {}

        args_raw = tool_calls[0].function.arguments or "{}"
        data = json.loads(args_raw)

        # 스키마에 없는 키 제거 (안전)
        allowed_keys = {
            *(x["name"] for x in (schema.get("required") or [])),
            *(x["name"] for x in (schema.get("optional") or [])),
        }
        cleaned = {k: v for k, v in (data or {}).items() if k in allowed_keys}

        # 경로 문자열 정리(따옴표 제거, 슬래시 정규화) 정도의 라이트 전처리
        for spec in (schema.get("required") or []) + (schema.get("optional") or []):
            if spec.get("type") == "path" and spec["name"] in cleaned and isinstance(cleaned[spec["name"]], str):
                s = cleaned[spec["name"]].strip().strip('"').strip("'")
                s = s.replace("/", "\\")
                cleaned[spec["name"]] = s

        return cleaned
    except Exception:
        # 실패 시 빈 dict (validator가 텍스트 규칙 기반/후속 요청으로 보강)
        return {}
