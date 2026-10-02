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


def _summary_of(resp) -> str:
    """取第一次工具调用的结果文本。

    轨迹里的 summary 被截到 300 字符，所以断言一律用子串匹配，不做 JSON 解析 ——
    定损的结果有上千字符，解析必然失败。
    """
    trace = resp.json()["tool_trace"]
    assert trace, "应当至少有一次工具调用"
    return trace[0]["summary"]


class TestAssessDisaster:
    def test_assesses_owned_record(self, client, auth_headers, monkeypatch, detection_record):
        did = detection_record["detection_id"]
        _patch_llm(
            monkeypatch,
            [
                _tool_call("assess_disaster", {"detection_id": did, "area_mu": 100, "crop_type": "玉米"}),
                {"content": "算完了"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "给这条记录做定损"}, headers=auth_headers
        )
        summary = _summary_of(resp)
        assert '"plot_area_mu": 100' in summary, summary
        assert '"detection_id": %d' % did in summary, summary

    def test_warns_when_economic_params_missing(self, client, auth_headers, monkeypatch, detection_record):
        """未给亩产/单价时总损失必然是 0。原响应对此毫无提示，模型极易据此
        汇报「无损失」—— 警告必须出现，且要排在结果最前面以免被截掉。"""
        _patch_llm(
            monkeypatch,
            [
                _tool_call("assess_disaster", {"detection_id": detection_record["detection_id"], "area_mu": 100}),
                {"content": "算完了"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "定损"}, headers=auth_headers
        )
        summary = _summary_of(resp)
        assert "不代表没有损失" in summary, summary
        # 必须排在第一位：轨迹里的结果被截到 300 字符，而 levels 一项就占掉大半，
        # 警告若排在后面会被截掉，模型与人都看不到。
        assert summary.startswith('{"warning"'), summary

    def test_warns_when_only_one_economic_param_is_zero(
        self, client, auth_headers, monkeypatch, detection_record
    ):
        """损失 = 面积 × 亩产 × 单价 × 减产比例，**任一项为 0 结果就是 0**。

        判据若写成「亩产与单价全都为 0」，只填了一个的情况就会漏掉：
        亩产 0、单价 2.4 时 any() 为真，告警被抑制，而 total_loss 仍是 0，
        模型照样会向用户汇报「无损失」。这条是那个漏网的回归测试。
        """
        _patch_llm(
            monkeypatch,
            [
                _tool_call(
                    "assess_disaster",
                    {
                        "detection_id": detection_record["detection_id"],
                        "area_mu": 100,
                        "yield_per_mu": 0,
                        "price_per_kg": 2.4,
                    },
                ),
                {"content": "算完了"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "定损"}, headers=auth_headers
        )
        summary = _summary_of(resp)
        assert summary.startswith('{"warning"'), summary
        # 警告里要点名是哪个参数缺了，否则用户不知道该补什么
        assert "亩产" in summary, summary

    def test_no_warning_when_params_given(self, client, auth_headers, monkeypatch, detection_record):
        _patch_llm(
            monkeypatch,
            [
                _tool_call(
                    "assess_disaster",
                    {
                        "detection_id": detection_record["detection_id"],
                        "area_mu": 100,
                        "yield_per_mu": 500,
                        "price_per_kg": 2.4,
                    },
                ),
                {"content": "算完了"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "定损"}, headers=auth_headers
        )
        summary = _summary_of(resp)
        assert "不代表没有损失" not in summary, summary

    def test_rejects_other_users_record(self, client, admin_headers, monkeypatch, detection_record):
        _patch_llm(
            monkeypatch,
            [
                _tool_call("assess_disaster", {"detection_id": detection_record["detection_id"]}),
                {"content": "查不到"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "定损"}, headers=admin_headers
        )
        trace = resp.json()["tool_trace"]
        assert trace[0]["ok"] is False
        # 不区分「不存在」与「不属于你」
        assert "检测记录不存在" in trace[0]["summary"]


class TestSeriesTrend:
    def _make_series(self, client, auth_headers, detection_id, area_mu=100):
        created = client.post(
            "/series",
            json={"name": "绥化北林区玉米", "location": "黑龙江省绥化市", "area_mu": area_mu},
            headers=auth_headers,
        )
        assert created.status_code == 200, created.text
        series_id = created.json()["series"]["id"]
        attached = client.post(
            f"/series/{series_id}/records",
            json={"records": [{"detection_id": detection_id, "t1_time": "2024-05", "t2_time": "2024-09"}]},
            headers=auth_headers,
        )
        assert attached.status_code == 200, attached.text
        return series_id

    def test_returns_trend_for_owned_series(self, client, auth_headers, monkeypatch, detection_record):
        series_id = self._make_series(client, auth_headers, detection_record["detection_id"])
        _patch_llm(
            monkeypatch,
            [
                _tool_call("get_series_trend", {"series_id": series_id}),
                {"content": "看完了"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "这个序列变化快不快"}, headers=auth_headers
        )
        summary = _summary_of(resp)
        assert "interval_count" in summary, summary

    def test_rejects_series_not_owned(self, client, admin_headers, monkeypatch, auth_headers, detection_record):
        series_id = self._make_series(client, auth_headers, detection_record["detection_id"])
        _patch_llm(
            monkeypatch,
            [
                _tool_call("get_series_trend", {"series_id": series_id}),
                {"content": "查不到"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "看趋势"}, headers=admin_headers
        )
        trace = resp.json()["tool_trace"]
        assert trace[0]["ok"] is False
        assert "序列不存在" in trace[0]["summary"]

    def test_list_series_reports_member_count(self, client, auth_headers, monkeypatch, detection_record):
        series_id = self._make_series(client, auth_headers, detection_record["detection_id"])
        _patch_llm(
            monkeypatch,
            [_tool_call("list_series", {}), {"content": "列完了"}],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "我有哪些序列"}, headers=auth_headers
        )
        summary = _summary_of(resp)
        assert '"member_count": 1' in summary, summary
        assert '"series_id": %d' % series_id in summary, summary

    def test_list_series_is_user_scoped(self, client, admin_headers, monkeypatch, auth_headers, detection_record):
        """管理员查别人的序列必须查不到 —— 与 list_detections 同一条规矩。"""
        self._make_series(client, auth_headers, detection_record["detection_id"])
        _patch_llm(
            monkeypatch,
            [_tool_call("list_series", {}), {"content": "列完了"}],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "我有哪些序列"}, headers=admin_headers
        )
        summary = _summary_of(resp)
        assert '"count": 0' in summary, summary

    def test_list_series_announces_truncation(self, client, auth_headers, monkeypatch):
        """截断必须说出来，而且排在最前面。

        这个工具的**唯一**用途是把用户嘴里的序列名字换成 series_id；
        静默截断会让模型在列表里找不到目标，进而向用户断言「没有这个序列」——
        那是错误的结论，不是「没查到」。排在最后则会被 300 字符的轨迹截没。
        """
        # 直接落库而不是走接口：POST /series 限流 20/分钟，造 25 个会被拦
        from backend.app.models.database import SessionLocal
        from backend.app.models.series import ImageSeriesDB
        from backend.app.models.user import UserDB

        db = SessionLocal()
        try:
            uid = db.query(UserDB).filter(UserDB.username == "testuser").first().id
            for i in range(25):
                db.add(ImageSeriesDB(user_id=uid, name=f"序列{i:02d}"))
            db.commit()
        finally:
            db.close()

        _patch_llm(monkeypatch, [_tool_call("list_series", {}), {"content": "列完了"}])
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "我有哪些序列"}, headers=auth_headers
        )
        summary = _summary_of(resp)
        assert summary.startswith('{"truncated"'), summary
        assert "25" in summary, summary
        assert '"count": 20' in summary, summary

    def test_rejects_missing_series(self, client, auth_headers, monkeypatch):
        _patch_llm(
            monkeypatch,
            [
                _tool_call("get_series_trend", {"series_id": 999999}),
                {"content": "查不到"},
            ],
        )
        resp = client.post(
            "/agent/execute-tools", data={"instruction": "看趋势"}, headers=auth_headers
        )
        trace = resp.json()["tool_trace"]
        assert trace[0]["ok"] is False
        assert "序列不存在" in trace[0]["summary"]
