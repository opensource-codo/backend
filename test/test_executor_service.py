# test/test_executor_service.py
import asyncio
import os
import sys
import services.executor_service as ex

os.environ["OPENAI_API_KEY"] = "test"

def test_paste_planner_hotkey():
    params = {"combo": ["Control", "V"]}
    res = asyncio.run(ex.plan_action("paste", params))
    assert res["ok"] is True
    assert res["exec"]["kind"] == "hotkey"
    assert res["exec"]["payload"]["combo"] == ["ctrl", "v"]

def test_generic_script_planner_with_db_patch(monkeypatch):
    fake_row = {
        "function_key": "flush_dns",
        "function_name": "DNS 캐시 비우기",
        "script_path": "",
        "script_command": "Clear-DnsClientCache",
        "shortcut": None,
    }

    def fake_get(key):
        return fake_row if key == "flush_dns" else None

    # 레지스트리/리스크 판정 단순화
    monkeypatch.setattr("services.executor_service._HANDLER_REGISTRY", {}, raising=True)
    monkeypatch.setattr("services.executor_service._sanitize_params", lambda p: p or {}, raising=True)
    monkeypatch.setattr("services.executor_service._classify_risk", lambda c: "safe", raising=True)

    # executor_service가 import하는 table_access를 가짜 모듈로 주입
    import types as _t
    fake_mod = _t.ModuleType("services.table_access")
    fake_mod.get_function_by_key = fake_get
    sys.modules["services.table_access"] = fake_mod

    res = asyncio.run(ex.plan_action("flush_dns", parameters={}))

    assert res["ok"] is True
    assert res["exec"]["kind"] == "shell"
    assert res["exec"]["payload"]["shell"] == "powershell"  # DEFAULT_SHELL 폴백 확인
    assert "Clear-DnsClientCache" in res["exec"]["payload"]["command"]

def test_generic_script_planner_requires_confirmation():
    planner = ex.GenericScriptPlanner(
        script_path="",
        script_command="Clear-RecycleBin -Force",
        shortcut=None,
        cwd=None,
        shell="powershell",
    )
    res = asyncio.run(planner.plan({}))
    assert res.ok is True
    assert res.exec["requiresConfirmation"] is True
