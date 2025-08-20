# tests/test_param_extractor.py
import json
import types
import builtins
os.environ["OPENAI_API_KEY"] = "test"
import services.param_extractor as pe

class FakeToolFunction:
    def __init__(self, arguments: str):
        self.arguments = arguments

class FakeMessage:
    def __init__(self, tool_calls=None):
        self.tool_calls = tool_calls or []

class FakeChoice:
    def __init__(self, message):
        self.message = message

class FakeResp:
    def __init__(self, choices):
        self.choices = choices

class FakeChatCompletions:
    def __init__(self, payload_args):
        self._payload_args = payload_args

    def create(self, **kwargs):
        # kwargs에는 model, messages, tools, tool_choice 등이 들어옴
        # 스키마를 확인하고 적절한 tool_calls 리턴
        # 이 테스트에선 "path"와 "bool" 포함 케이스를 검증
        # 유효한 인자만 추출되어야 한다(스키마 외 키 제거)

        # 페이크로, 항상 아래 arguments를 반환
        arguments = json.dumps({
            "target_path": r'C:\Temp\logs',   # path 타입
            "enable": True,                   # bool 타입
            "unknown": "should_be_dropped"    # 스키마에 없어서 제거되어야 함
        })
        tool_calls = [types.SimpleNamespace(function=FakeToolFunction(arguments))]
        msg = FakeMessage(tool_calls=tool_calls)
        return FakeResp([FakeChoice(msg)])

class FakeOpenAI:
    def __init__(self):
        self.chat = types.SimpleNamespace(completions=FakeChatCompletions(None))

def test_extract_params_llm_basic(monkeypatch):
    # 1) 클라이언트 주입 (코드에 set_openai_client 추가했다고 가정)
    pe.set_openai_client(FakeOpenAI())

    # 2) 스키마 정의 (required/optional)
    schema = {
        "required": [
            {"name": "target_path", "type": "path", "description": "대상 경로"},
        ],
        "optional": [
            {"name": "enable", "type": "bool", "description": "기능 on/off"},
        ],
    }

    intent = "sample_intent"
    text = "C:\\Temp\\logs 폴더에 대해 기능 켜줘"

    out = pe.extract_params_llm(intent=intent, text=text, schema=schema, model="dummy-model")
    # 기대:
    # - unknown 키는 제거
    # - path는 \로 정규화, 따옴표 제거
    # - bool은 그대로
    assert set(out.keys()) == {"target_path", "enable"}
    assert out["target_path"] == r"C:\Temp\logs"
    assert out["enable"] is True

def test_extract_params_llm_empty_input(monkeypatch):
    pe.set_openai_client(FakeOpenAI())
    assert pe.extract_params_llm("", "text", {"required": []}) == {}
    assert pe.extract_params_llm("intent", "", {"required": []}) == {}
    assert pe.extract_params_llm("intent", "text", {}) == {}
