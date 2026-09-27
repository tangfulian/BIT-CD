"""工具调用通道（/agent/execute-tools）的测试。

模型侧一律打桩：这一层要测的是**通道自身的语义** —— 身份从哪来、
路径白名单有没有生效、管理员旁路有没有被掐掉 —— 而不是模型的行为。
"""
import io
import json
import re

import numpy as np
from PIL import Image

# 附件清单在系统提示里的形态：两个空格 + 路径 + 空格 + （文件名 ...）
_ATTACHMENT_RE = re.compile(r"^\s{2}(\S+)\s+（文件名", re.M)


def _png_bytes() -> io.BytesIO:
    arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    buf.seek(0)
    return buf


def _tool_call(name: str, arguments: dict, call_id: str = "call_1") -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        ],
    }


def _patch_llm(monkeypatch, script: list[dict]):
    """按脚本逐轮喂模型回复；脚本用尽后重复最后一条。"""
    state = {"n": 0}

    def _fake_post_chat(messages, tools):
        idx = min(state["n"], len(script) - 1)
        state["n"] += 1
        return script[idx]

    monkeypatch.setattr(
        "backend.app.services.tool_agent_service._post_chat", _fake_post_chat
    )


class TestChannelAccess:
    def test_requires_auth(self, client):
        resp = client.post("/agent/execute-tools", data={"instruction": "你好"})
        assert resp.status_code in (401, 403)

    def test_regular_user_is_allowed(self, client, auth_headers, monkeypatch):
        """工具通道刻意只要求登录，不要求 admin —— 它全程以本人身份执行，
        没有管理员旁路、没有 Chrome，能做的事与用户自己点界面相同。"""
        _patch_llm(monkeypatch, [{"content": "好的"}])
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "你好"}, headers=auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["success"] is True
        assert body["final_result"] == "好的"


class TestToolSchemaSafety:
    def test_schemas_never_expose_identity_params(self):
        from backend.app.services.tool_agent_service import _tool_schemas

        for tool in _tool_schemas([]):
            props = tool["function"]["parameters"].get("properties", {})
            assert "user_id" not in props, f"{tool['function']['name']} 暴露了 user_id"
            assert "is_admin" not in props, f"{tool['function']['name']} 暴露了 is_admin"

    def test_model_enum_only_lists_available_models(self):
        from backend.app.services.detect_service import model_availability
        from backend.app.services.tool_agent_service import _tool_schemas

        run = next(t for t in _tool_schemas([]) if t["function"]["name"] == "run_detection")
        enum = run["function"]["parameters"]["properties"]["model"]["enum"]
        assert enum == [n for n, ok in model_availability().items() if ok]


class TestPathAllowlist:
    def test_rejects_path_not_in_attachments(self, client, auth_headers, monkeypatch):
        """提示词注入若想让模型去读白名单外的文件，必须被拒。"""
        _patch_llm(
            monkeypatch,
            [
                _tool_call(
                    "run_detection",
                    {"image1": "/etc/passwd", "image2": "/etc/passwd", "model": "BIT"},
                ),
                {"content": "被拒绝了"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools",
            data={"instruction": "跑检测"},
            files=[("files", ("t1.png", _png_bytes(), "image/png"))],
            headers=auth_headers,
        )
        trace = resp.json()["tool_trace"]
        assert len(trace) == 1
        assert trace[0]["ok"] is False
        assert "不在本次可用附件里" in trace[0]["summary"]

    def test_rejects_when_no_attachments_at_all(self, client, auth_headers, monkeypatch):
        _patch_llm(
            monkeypatch,
            [
                _tool_call(
                    "run_detection",
                    {"image1": "/app/.env", "image2": "/app/.env", "model": "BIT"},
                ),
                {"content": "没有附件"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "跑检测"}, headers=auth_headers
        )
        trace = resp.json()["tool_trace"]
        assert trace[0]["ok"] is False
        assert "不在本次可用附件里" in trace[0]["summary"]


class TestRunDetection:
    def test_runs_and_records_under_caller(self, client, auth_headers, monkeypatch):
        """走通完整链路：附件落盘 -> 模型给出工具调用 -> 服务层检测 -> 落库。

        路径从系统提示里现取，确保测的是「模型用我们给的路径」这条真实路径，
        而不是测试自己编一个。
        """
        state = {"n": 0}

        def _fake_post_chat(messages, tools):
            state["n"] += 1
            if state["n"] == 1:
                paths = _ATTACHMENT_RE.findall(messages[0]["content"])
                assert len(paths) == 2, f"系统提示里应列出两个附件路径，实际 {paths}"
                return _tool_call(
                    "run_detection",
                    {
                        "image1": paths[0],
                        "image2": paths[1],
                        "model": "BIT",
                        "threshold": 0.5,
                    },
                )
            return {"content": "检测完成"}

        monkeypatch.setattr(
            "backend.app.services.tool_agent_service._post_chat", _fake_post_chat
        )

        resp = client.post(
            "/agent/execute-tools",
            data={"instruction": "用附件跑一次 BIT 检测，阈值 0.5"},
            files=[
                ("files", ("t1.png", _png_bytes(), "image/png")),
                ("files", ("t2.png", _png_bytes(), "image/png")),
            ],
            headers=auth_headers,
        )
        body = resp.json()
        assert body["success"] is True
        trace = body["tool_trace"]
        assert len(trace) == 1
        assert trace[0]["ok"] is True
        assert trace[0]["tool"] == "run_detection"

        payload = json.loads(trace[0]["summary"])
        # conftest 的全局假桩固定返回 ratio 3.81
        assert payload["change_ratio_percent"] == 3.81
        assert payload["detection_id"] is not None
        # 刻意不回灌图片 URL，避免模型把它们抄进回答
        assert "mask" not in payload


class TestHistoryIsolation:
    def test_admin_gets_no_bypass(self, client, auth_headers, admin_headers, monkeypatch, detection_record):
        """detection_record 属于 auth_headers 那个用户；管理员来查必须查不到。

        history.py 的 HTTP 接口在 role == "admin" 时会返回全库记录，而 Agent
        历史上正是以 admin 身份跑的 —— 工具层必须掐掉这条旁路。
        """
        _patch_llm(
            monkeypatch,
            [_tool_call("list_detections", {"limit": 10}), {"content": "看完了"}],
        )
        resp = client.post(
            "/agent/execute-tools",
            data={"instruction": "看看我的检测历史"},
            headers=admin_headers,
        )
        summary = json.loads(resp.json()["tool_trace"][0]["summary"])
        assert summary["count"] == 0

    def test_owner_sees_own_record(self, client, auth_headers, monkeypatch, detection_record):
        _patch_llm(
            monkeypatch,
            [_tool_call("list_detections", {"limit": 10}), {"content": "看完了"}],
        )
        resp = client.post(
            "/agent/execute-tools",
            data={"instruction": "看看我的检测历史"},
            headers=auth_headers,
        )
        summary = json.loads(resp.json()["tool_trace"][0]["summary"])
        assert summary["count"] == 1
        assert summary["items"][0]["detection_id"] == detection_record["detection_id"]

    def test_get_detection_rejects_other_users_record(
        self, client, admin_headers, monkeypatch, detection_record
    ):
        _patch_llm(
            monkeypatch,
            [
                _tool_call("get_detection", {"detection_id": detection_record["detection_id"]}),
                {"content": "查不到"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools",
            data={"instruction": "查这条记录"},
            headers=admin_headers,
        )
        trace = resp.json()["tool_trace"]
        assert trace[0]["ok"] is False
        # 不区分"不存在"与"不属于你"，避免泄露他人记录的存在性
        assert "不属于你" in trace[0]["summary"]


class TestParameterValidation:
    def test_rejects_out_of_range_threshold(self, client, auth_headers, monkeypatch):
        state = {"n": 0}

        def _fake_post_chat(messages, tools):
            state["n"] += 1
            if state["n"] == 1:
                paths = _ATTACHMENT_RE.findall(messages[0]["content"])
                return _tool_call(
                    "run_detection",
                    {"image1": paths[0], "image2": paths[0], "model": "BIT", "threshold": 7.5},
                )
            return {"content": "阈值不合法"}

        monkeypatch.setattr(
            "backend.app.services.tool_agent_service._post_chat", _fake_post_chat
        )
        resp = client.post(
            "/agent/execute-tools",
            data={"instruction": "阈值 7.5"},
            files=[("files", ("t1.png", _png_bytes(), "image/png"))],
            headers=auth_headers,
        )
        trace = resp.json()["tool_trace"]
        assert trace[0]["ok"] is False
        assert "0~1" in trace[0]["summary"]

    def test_clamps_absurd_limit(self, client, auth_headers, monkeypatch):
        """HTTP 那边 limit 可到 500，工具侧必须强制收窄，否则一次灌爆上下文。"""
        _patch_llm(
            monkeypatch,
            [_tool_call("list_detections", {"limit": 100000}), {"content": "好"}],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "列出全部"}, headers=auth_headers
        )
        # 没有记录时应返回 0 条而不是报错，且不应因 limit 过大而炸
        assert resp.json()["tool_trace"][0]["ok"] is True


class TestLoopBounds:
    def test_stops_at_max_rounds_and_reports_failure(self, client, auth_headers, monkeypatch):
        """模型反复调用工具不肯收敛时，必须停下来并如实报告，而不是无限打转。"""
        _patch_llm(monkeypatch, [_tool_call("list_models", {})])
        resp = client.post(
            "/agent/execute-tools",
            data={"instruction": "一直查", "max_rounds": 3},
            headers=auth_headers,
        )
        body = resp.json()
        assert body["success"] is False
        assert body["total_steps"] == 3
        assert "3 轮" in body["final_result"]

    def test_unknown_tool_is_reported_not_crashed(self, client, auth_headers, monkeypatch):
        _patch_llm(
            monkeypatch,
            [_tool_call("delete_everything", {}), {"content": "没有这个工具"}],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "删库"}, headers=auth_headers
        )
        trace = resp.json()["tool_trace"]
        assert trace[0]["ok"] is False
        assert "没有名为" in trace[0]["summary"]
