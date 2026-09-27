"""灾害定损的回归测试。

这个功能的风险不在算错数，而在**把假设当结论**：模型给出的是"变化置信度"，
不是"减产率"，两者之间没有经过验证的换算。所以除了算术正确性，这里还专门
锁住"假设必须被标成假设"这件事。
"""
import numpy as np
import pytest

from backend.app.services.disaster_service import (
    DEFAULT_GRADE_BOUNDS,
    DEFAULT_LOSS_RATES,
    DRAFT_MARKER,
    assess,
    ensure_draft_label,
    grade_severity,
)


def _graded_fixture():
    """10×10=100 像素的影像，其中**只有 50 个像素发生变化**，四档各 20/15/10/5。

    掩膜刻意只覆盖一半 —— 早先的 fixture 让全部像素都变化，变化占比恰好是
    100%，于是"按总像素摊派"与"按变化像素摊派"给出完全一样的结果，
    掩盖了受灾面积被高估的 bug。留一半不变才能把两者区分开。
    """
    score = np.zeros((10, 10), np.float32)
    score.flat[:20] = 0.30    # 轻度（< 0.60）
    score.flat[20:35] = 0.65  # 中度
    score.flat[35:45] = 0.80  # 重度
    score.flat[45:50] = 0.95  # 绝收
    mask = np.zeros((10, 10), np.uint8)
    mask.flat[:50] = 255      # 只有前 50 个像素属于变化区
    return score, mask


class TestGradeSeverity:
    def test_counts_match_known_distribution(self):
        score, mask = _graded_fixture()
        g = grade_severity(score, mask)
        assert [g[k]["pixels"] for k in ("mild", "moderate", "severe", "total")] == [20, 15, 10, 5]

    def test_shares_sum_to_one(self):
        score, mask = _graded_fixture()
        g = grade_severity(score, mask)
        assert abs(sum(v["share"] for v in g.values()) - 1.0) < 1e-9

    def test_boundary_is_left_closed(self):
        """恰好等于下界的像素归入上一档 —— 分级区间左闭右开，不能有缝也不能重叠。"""
        score = np.array([[0.60, 0.75, 0.92]], np.float32)
        mask = np.full((1, 3), 255, np.uint8)
        g = grade_severity(score, mask)
        assert g["mild"]["pixels"] == 0        # 0.60 已进入中度
        assert g["moderate"]["pixels"] == 1    # 0.75 已进入重度，故只剩 0.60
        assert g["severe"]["pixels"] == 1      # 0.92 已进入绝收
        assert g["total"]["pixels"] == 1

    def test_pixels_outside_mask_ignored(self):
        """掩膜外的像素不参与分级，哪怕 score 很高。"""
        score = np.full((4, 4), 0.99, np.float32)
        mask = np.zeros((4, 4), np.uint8)
        mask[0, 0] = 255
        g = grade_severity(score, mask)
        assert g["total"]["pixels"] == 1

    def test_no_change_yields_zeros(self):
        """零变化时不能除零。"""
        score = np.zeros((8, 8), np.float32)
        mask = np.zeros((8, 8), np.uint8)
        g = grade_severity(score, mask)
        assert all(v["pixels"] == 0 and v["share"] == 0.0 for v in g.values())

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            grade_severity(np.zeros((4, 4), np.float32), np.zeros((5, 5), np.uint8))

    def test_custom_bounds_respected(self):
        score, mask = _graded_fixture()
        g = grade_severity(score, mask, {"moderate": 0.9, "severe": 0.95, "total": 0.99})
        # 0.9 以下全部归轻度：20+15+10 = 45
        assert g["mild"]["pixels"] == 45


class TestAssessMath:
    def test_loss_per_level_and_total(self):
        """逐级金额与合计必须与手算一致。

        100 亩地块、影像 100 像素、其中 50 像素变化：
        各级面积 = 100 × 像素数/100 = 像素数本身。
        mild 20亩 × 500kg × 2元 × 0.2 = 4000
        """
        score, mask = _graded_fixture()
        r = assess(score, mask, area_mu=100, yield_per_mu=500, price_per_kg=2.0)
        got = {l["level"]: l["loss_yuan"] for l in r["levels"]}
        assert got == {"mild": 4000.0, "moderate": 6000.0,
                       "severe": 7000.0, "total": 5000.0}
        assert r["total_loss_yuan"] == 22000.0

    def test_affected_area_is_not_the_whole_plot(self):
        """回归：受灾面积必须按**总像素**摊派，不能把整块地都算成受灾。

        地块 100 亩、影像 100 像素、其中 50 像素变化 → 受灾 50 亩。
        早先按变化像素摊派，四级面积之和恒等于地块总面积，无论检出多少变化
        都会报出 100 亩受灾 —— 这是个 2 倍的高估，且变化占比越小时高估越离谱。
        """
        score, mask = _graded_fixture()
        r = assess(score, mask, area_mu=100, yield_per_mu=1, price_per_kg=1)
        assert r["affected_area_mu"] == 50.0
        assert r["affected_area_mu"] < r["plot_area_mu"]

    def test_tiny_change_does_not_report_whole_plot(self):
        """检出 1% 变化时，受灾面积就该是 1% —— 这条若挂说明分母又用错了。"""
        score = np.full((100, 100), 0.99, np.float32)
        mask = np.zeros((100, 100), np.uint8)
        mask.flat[:100] = 255          # 10000 像素中仅 100 个变化 = 1%
        r = assess(score, mask, area_mu=200, yield_per_mu=1, price_per_kg=1)
        assert r["affected_area_mu"] == pytest.approx(2.0, abs=0.01)

    def test_area_scales_with_plot_area(self):
        score, mask = _graded_fixture()
        r = assess(score, mask, area_mu=200, yield_per_mu=1, price_per_kg=1)
        got = {l["level"]: l["area_mu"] for l in r["levels"]}
        # 200 亩 → 各级 = 200 × 像素数/100
        assert got == {"mild": 40.0, "moderate": 30.0, "severe": 20.0, "total": 10.0}
        assert r["affected_area_mu"] == 100.0

    def test_zero_area_is_all_zero(self):
        score, mask = _graded_fixture()
        r = assess(score, mask, area_mu=0, yield_per_mu=500, price_per_kg=2.0)
        assert r["total_loss_yuan"] == 0.0
        assert r["affected_area_mu"] == 0.0

    def test_no_change_does_not_divide_by_zero(self):
        score = np.zeros((8, 8), np.float32)
        mask = np.zeros((8, 8), np.uint8)
        r = assess(score, mask, area_mu=100, yield_per_mu=500, price_per_kg=2.0)
        assert r["total_loss_yuan"] == 0.0
        assert r["change_pixel"] == 0

    def test_custom_loss_rates_change_result(self):
        score, mask = _graded_fixture()
        zero = assess(score, mask, 100, 500, 2.0,
                      loss_rates={k: 0.0 for k in DEFAULT_LOSS_RATES})
        assert zero["total_loss_yuan"] == 0.0

    def test_survey_cost_saving(self):
        score, mask = _graded_fixture()
        r = assess(score, mask, area_mu=100, yield_per_mu=500, price_per_kg=2.0)
        s = r["survey_cost"]
        # 默认 10 元/亩 人工，3.5 元/亩 遥感；查勘成本按**受灾面积**算
        # （只查受灾的地块，不是整块地），本 fixture 受灾 50 亩
        assert r["affected_area_mu"] == 50.0
        assert s["manual_cost_yuan"] == 500.0
        assert s["remote_cost_yuan"] == 175.0
        assert s["saving_yuan"] == 325.0


class TestHonestyFields:
    """防止将来有人把假设值当成系统测算结论输出。"""

    def test_assumptions_present_and_labelled(self):
        score, mask = _graded_fixture()
        r = assess(score, mask, 100, 500, 2.0)
        assert r["assumptions"], "assumptions 不能为空"
        for a in r["assumptions"]:
            assert a["note"], f"{a['key']} 缺来源说明"
            assert a["label"]

    def test_assumptions_cover_every_user_supplied_number(self):
        """亩产、单价、四级减产比例、分级下界、查勘单价都要能被列出来。"""
        score, mask = _graded_fixture()
        r = assess(score, mask, 100, 500, 2.0)
        keys = {a["key"] for a in r["assumptions"]}
        assert {"yield_per_mu", "price_per_kg", "grade_bounds", "survey_cost"} <= keys
        assert {f"loss_rate.{lvl}" for lvl in DEFAULT_LOSS_RATES} <= keys

    def test_formula_is_echoed(self):
        score, mask = _graded_fixture()
        r = assess(score, mask, 100, 500, 2.0)
        assert r["formula"]["loss"] and r["formula"]["area"]

    def test_draft_label_is_idempotent(self):
        once = ensure_draft_label("正文")
        twice = ensure_draft_label(once)
        assert once.count(DRAFT_MARKER) == 1
        assert twice.count(DRAFT_MARKER) == 1

    def test_draft_label_added_when_model_omits_it(self):
        assert DRAFT_MARKER in ensure_draft_label("模型没有输出标记")


class TestParamsEndpoint:
    def test_requires_auth(self, client):
        assert client.get("/disaster/params").status_code == 401

    def test_returns_defaults_with_source(self, client, auth_headers):
        resp = client.get("/disaster/params", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["crop_params"], "作物默认参数不能为空"
        assert data["source_note"], "查勘成本必须给出处"
        assert data["survey_cost_ranges"]["manual_per_mu"]


class TestAssessEndpoint:
    def test_requires_auth(self, client):
        assert client.post("/disaster/assess", json={"detection_id": 1}).status_code == 401

    def test_nonexistent_record_404(self, client, auth_headers):
        resp = client.post("/disaster/assess", json={"detection_id": 999999},
                           headers=auth_headers)
        assert resp.status_code == 404

    def test_other_users_record_404(self, client, auth_headers, detection_record):
        """别人的记录与不存在的记录返回同一个 404，不泄露存在性。"""
        client.post("/register", json={"username": "other", "password": "otherpass123"})
        tok = client.post("/login", json={"username": "other", "password": "otherpass123"}).json()["token"]
        resp = client.post(
            "/disaster/assess",
            json={"detection_id": detection_record["detection_id"]},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 404

    def test_happy_path(self, client, auth_headers, detection_record):
        resp = client.post(
            "/disaster/assess",
            json={"detection_id": detection_record["detection_id"], "area_mu": 100},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        r = resp.json()["result"]
        # mock 的检测固定为 2500/65536 变化像素、score 恒 0.9
        assert r["measured"]["change_pixel"] == 2500
        assert r["change_pixel"] == 2500
        # score 0.9 落在 [0.75, 0.92) → 重度
        assert [l["pixels"] for l in r["levels"]] == [0, 0, 2500, 0]
        assert r["disclaimer"]
        assert r["assumptions"]

    def test_record_without_score_map_400(self, client, auth_headers, detection_record):
        """没有概率图的记录不能定损，且要给出可读原因。"""
        from backend.app.models.database import SessionLocal
        from backend.app.models.detection import DetectionResultDB

        db = SessionLocal()
        rec = db.query(DetectionResultDB).filter(
            DetectionResultDB.id == detection_record["detection_id"]
        ).first()
        rec.score_url = ""
        db.commit()
        db.close()

        resp = client.post(
            "/disaster/assess",
            json={"detection_id": detection_record["detection_id"]},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "概率图" in resp.json()["detail"]

    def test_non_monotonic_bounds_rejected(self, client, auth_headers, detection_record):
        resp = client.post(
            "/disaster/assess",
            json={
                "detection_id": detection_record["detection_id"],
                "area_mu": 100,
                "grade_bounds": {"moderate": 0.9, "severe": 0.7, "total": 0.95},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_custom_yield_changes_loss(self, client, auth_headers, detection_record):
        base = {"detection_id": detection_record["detection_id"], "area_mu": 100}
        a = client.post("/disaster/assess", json={**base, "yield_per_mu": 100, "price_per_kg": 1},
                        headers=auth_headers).json()["result"]
        b = client.post("/disaster/assess", json={**base, "yield_per_mu": 200, "price_per_kg": 1},
                        headers=auth_headers).json()["result"]
        assert b["total_loss_yuan"] == pytest.approx(a["total_loss_yuan"] * 2)

    def test_crop_type_supplies_defaults(self, client, auth_headers, detection_record):
        """选了作物就该带上该作物的示例亩产/单价，并在 assumptions 里回显。"""
        resp = client.post(
            "/disaster/assess",
            json={"detection_id": detection_record["detection_id"],
                  "area_mu": 100, "crop_type": "大豆连作"},
            headers=auth_headers,
        )
        r = resp.json()["result"]
        got = {a["key"]: a["value"] for a in r["assumptions"]}
        assert got["yield_per_mu"] == 140.0


class TestNarrativeEndpoint:
    def test_requires_auth(self, client):
        assert client.post("/disaster/narrative", json={"detection_id": 1}).status_code == 401

    def test_draft_carries_marker_and_flags(self, client, auth_headers, detection_record):
        """conftest 的假 chat 不输出草稿标记，服务端必须自行补上。"""
        resp = client.post(
            "/disaster/narrative",
            json={"detection_id": detection_record["detection_id"], "area_mu": 100},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert DRAFT_MARKER in data["draft"]
        assert data["draft_label"]
        assert data["uses_image"] is False
        assert "未接收任何影像" in data["image_disclaimer"]

    def test_narrative_does_not_write_change_type(self, client, auth_headers, detection_record):
        """草稿绝不能回写记录字段 —— 一旦写进去，草稿就被洗成了记录上的既有事实。"""
        did = detection_record["detection_id"]
        before = client.get("/history?limit=500", headers=auth_headers).json()["data"]
        before_rec = next(r for r in before if r["id"] == did)

        client.post("/disaster/narrative",
                    json={"detection_id": did, "area_mu": 100},
                    headers=auth_headers)

        after = client.get("/history?limit=500", headers=auth_headers).json()["data"]
        after_rec = next(r for r in after if r["id"] == did)
        assert after_rec["change_type"] == before_rec["change_type"]
        assert after_rec["ai_change_type"] == before_rec["ai_change_type"]
