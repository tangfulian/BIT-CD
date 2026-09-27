"""多时相序列与趋势分析的回归测试。

重点锁三件事：
  1. 排序依据是**影像日期**，不是记录创建时间、也不是挂载顺序。
  2. 缺少日期/日期冲突时明确报错，不静默改写既有记录。
  3. 分析结果里必须带 caveats —— 防止"启发式突变点"被当成统计结论展示。

注意：测试库走 Base.metadata.create_all（conftest.py:22），**绕过 Alembic**，
所以本文件覆盖不到迁移的正确性。迁移只能靠启动应用后手工查表验证。
"""
import pytest

from backend.app.services.series_service import (
    _linear_fit,
    analyze_trend,
    build_intervals,
    parse_month,
)


def _rec(did, t1, t2, ratio=3.81, model="BIT"):
    return {
        "detection_id": did,
        "t1_time": t1,
        "t2_time": t2,
        "ratio": ratio,
        "change_pixel": 2500,
        "total_pixel": 65536,
        "model": model,
        "change_type": "",
    }


class TestParseMonth:
    def test_valid(self):
        assert parse_month("2024-05").isoformat() == "2024-05-01"
        assert parse_month("2024-5").isoformat() == "2024-05-01"

    @pytest.mark.parametrize("bad", ["", None, "abc", "2024", "2024-13", "2024-00",
                                     "2024-05-01", "1899-01", "2201-01"])
    def test_invalid(self, bad):
        assert parse_month(bad) is None


class TestLinearFit:
    def test_perfect_line(self):
        slope, intercept, r2 = _linear_fit([0, 1, 2], [10, 20, 30])
        assert slope == 10.0
        assert r2 == 1.0

    def test_constant_y_has_undefined_r2(self):
        """y 全相同时 R² 无定义，必须返回 None，不能给个漂亮的 1.0。"""
        slope, intercept, r2 = _linear_fit([0, 1, 2], [5, 5, 5])
        assert slope == 0.0
        assert r2 is None

    def test_too_few_points(self):
        assert _linear_fit([0], [1]) is None

    def test_all_x_equal(self):
        assert _linear_fit([3, 3, 3], [1, 2, 3]) is None


class TestBuildIntervals:
    def test_sorts_by_date_not_input_order(self):
        recs = [_rec(3, "2022-05", "2023-05"), _rec(1, "2020-05", "2021-05"),
                _rec(2, "2021-05", "2022-05")]
        iv, _ = build_intervals(recs)
        assert [i["detection_id"] for i in iv] == [1, 2, 3]

    def test_skips_missing_dates_with_reason(self):
        iv, skipped = build_intervals([_rec(1, "", ""), _rec(2, "2020-05", "2021-05")])
        assert len(iv) == 1
        assert len(skipped) == 1
        assert skipped[0]["detection_id"] == 1
        assert "日期" in skipped[0]["reason"]

    def test_skips_reversed_dates(self):
        iv, skipped = build_intervals([_rec(1, "2022-05", "2020-05")])
        assert iv == []
        assert "不晚于" in skipped[0]["reason"]

    def test_area_and_rate(self):
        iv, _ = build_intervals([_rec(1, "2020-05", "2021-05", ratio=10.0)], area_mu=100)
        assert iv[0]["change_area_mu"] == 10.0
        assert iv[0]["rate_area_per_year"] == pytest.approx(10.0, abs=0.01)

    def test_no_area_means_no_area_fields(self):
        iv, _ = build_intervals([_rec(1, "2020-05", "2021-05", ratio=10.0)], area_mu=0)
        assert iv[0]["change_area_mu"] is None
        assert iv[0]["rate_area_per_year"] is None
        assert iv[0]["rate_pct_per_year"] is not None


class TestAnalyzeTrend:
    def test_empty_does_not_crash(self):
        r = analyze_trend([])
        assert r["interval_count"] == 0
        assert r["fit"] is None
        assert r["caveats"]

    def test_single_interval_cannot_fit(self):
        iv, _ = build_intervals([_rec(1, "2020-05", "2021-05")])
        r = analyze_trend(iv, area_mu=100)
        assert r["fit"] is None
        assert any("少于 2 个" in c for c in r["caveats"])

    def test_equal_ratios_give_linear_cumulative(self):
        recs = [_rec(1, "2020-05", "2021-05", 2.0),
                _rec(2, "2021-05", "2022-05", 2.0),
                _rec(3, "2022-05", "2023-05", 2.0)]
        iv, _ = build_intervals(recs, area_mu=100)
        r = analyze_trend(iv, area_mu=100)
        # 每期增量相同 → 累计曲线是直线
        assert r["fit"]["r2"] == 1.0
        assert r["fit"]["n"] == 3
        assert r["summary"]["total_change_ratio_pct"] == 6.0
        assert r["summary"]["total_change_area_mu"] == 6.0

    def test_breakpoint_detected(self):
        recs = [_rec(1, "2020-05", "2021-05", 2.0),
                _rec(2, "2021-05", "2022-05", 2.0),
                _rec(3, "2022-05", "2023-05", 20.0)]
        iv, _ = build_intervals(recs)
        r = analyze_trend(iv)
        assert len(r["breakpoints"]) == 1
        assert r["breakpoints"][0]["detection_id"] == 3
        assert "倍" in r["breakpoints"][0]["reason"]
        assert any("启发式" in c for c in r["caveats"])

    def test_no_breakpoint_when_uniform(self):
        recs = [_rec(i, f"{2019+i}-05", f"{2020+i}-05", 3.0) for i in range(1, 5)]
        iv, _ = build_intervals(recs)
        assert analyze_trend(iv)["breakpoints"] == []

    def test_never_extrapolates(self):
        """明确不做未来外推 —— 结果里不该出现任何预测字段。"""
        recs = [_rec(1, "2020-05", "2021-05"), _rec(2, "2021-05", "2022-05")]
        iv, _ = build_intervals(recs)
        r = analyze_trend(iv)
        blob = str(r)
        for word in ("predict", "forecast", "外推值", "预测值"):
            assert word not in blob
        assert any("不外推" in c for c in r["caveats"])


class TestSeriesEndpoints:
    def _make_detection(self, client, auth_headers, t1="", t2=""):
        from tests.conftest import _fake_png_bytes
        resp = client.post(
            "/detect",
            files=[("img1", ("t1.png", _fake_png_bytes(), "image/png")),
                   ("img2", ("t2.png", _fake_png_bytes(), "image/png"))],
            data={"model": "BIT", "threshold": 0.5, "t1_time": t1, "t2_time": t2},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        return resp.json()["detection_id"]

    def test_requires_auth(self, client):
        assert client.get("/series").status_code == 401
        assert client.post("/series", json={"name": "x"}).status_code == 401

    def test_create_and_list(self, client, auth_headers):
        r = client.post("/series", json={"name": "试验田A", "location": "黑龙江省大庆市",
                                         "area_mu": 100}, headers=auth_headers)
        assert r.status_code == 200
        sid = r.json()["series"]["id"]
        data = client.get("/series", headers=auth_headers).json()["data"]
        assert any(s["id"] == sid and s["name"] == "试验田A" for s in data)

    def test_other_users_series_is_404(self, client, auth_headers):
        sid = client.post("/series", json={"name": "私有的"},
                          headers=auth_headers).json()["series"]["id"]
        client.post("/register", json={"username": "other", "password": "otherpass123"})
        tok = client.post("/login", json={"username": "other",
                                          "password": "otherpass123"}).json()["token"]
        resp = client.get(f"/series/{sid}", headers={"Authorization": f"Bearer {tok}"})
        assert resp.status_code == 404
        # 不存在的序列返回同样的 404，不泄露存在性
        assert resp.status_code == client.get("/series/999999",
                                              headers={"Authorization": f"Bearer {tok}"}).status_code

    def test_attach_orders_by_date_not_attach_order(self, client, auth_headers):
        sid = client.post("/series", json={"name": "s", "area_mu": 100},
                          headers=auth_headers).json()["series"]["id"]
        d1 = self._make_detection(client, auth_headers)
        d2 = self._make_detection(client, auth_headers)
        d3 = self._make_detection(client, auth_headers)
        # 故意乱序挂载
        resp = client.post(f"/series/{sid}/records", json={"records": [
            {"detection_id": d3, "t1_time": "2022-05", "t2_time": "2023-05"},
            {"detection_id": d1, "t1_time": "2020-05", "t2_time": "2021-05"},
            {"detection_id": d2, "t1_time": "2021-05", "t2_time": "2022-05"},
        ]}, headers=auth_headers)
        assert resp.status_code == 200
        recs = client.get(f"/series/{sid}", headers=auth_headers).json()["records"]
        assert [r["t1_time"] for r in recs] == ["2020-05", "2021-05", "2022-05"]
        assert [r["phase_index"] for r in recs] == [0, 1, 2]

    def test_attach_requires_dates(self, client, auth_headers):
        sid = client.post("/series", json={"name": "s"},
                          headers=auth_headers).json()["series"]["id"]
        did = self._make_detection(client, auth_headers)   # 无日期
        resp = client.post(f"/series/{sid}/records",
                           json={"records": [{"detection_id": did}]},
                           headers=auth_headers)
        assert resp.status_code == 400
        assert "日期" in resp.json()["detail"]

    def test_attach_rejects_date_conflict_without_overwriting(self, client, auth_headers):
        sid = client.post("/series", json={"name": "s"},
                          headers=auth_headers).json()["series"]["id"]
        did = self._make_detection(client, auth_headers, t1="2020-05", t2="2021-05")
        resp = client.post(f"/series/{sid}/records", json={"records": [
            {"detection_id": did, "t1_time": "2019-01", "t2_time": "2020-01"}
        ]}, headers=auth_headers)
        assert resp.status_code == 400
        assert "冲突" in resp.json()["detail"]
        # 原记录日期未被改写
        recs = client.get("/history?limit=500", headers=auth_headers).json()["data"]
        rec = next(r for r in recs if r["id"] == did)
        assert rec["t1_time"] == "2020-05"

    def test_attach_cannot_take_other_users_record(self, client, auth_headers):
        sid = client.post("/series", json={"name": "s"},
                          headers=auth_headers).json()["series"]["id"]
        did = self._make_detection(client, auth_headers)
        client.post("/register", json={"username": "other2", "password": "otherpass123"})
        tok = client.post("/login", json={"username": "other2",
                                          "password": "otherpass123"}).json()["token"]
        resp = client.post(f"/series/{sid}/records", json={"records": [
            {"detection_id": did, "t1_time": "2020-05", "t2_time": "2021-05"}
        ]}, headers={"Authorization": f"Bearer {tok}"})
        assert resp.status_code == 404   # 序列本身不属于该用户

    def test_delete_series_keeps_detections(self, client, auth_headers):
        sid = client.post("/series", json={"name": "s"},
                          headers=auth_headers).json()["series"]["id"]
        did = self._make_detection(client, auth_headers)
        client.post(f"/series/{sid}/records", json={"records": [
            {"detection_id": did, "t1_time": "2020-05", "t2_time": "2021-05"}
        ]}, headers=auth_headers)

        assert client.delete(f"/series/{sid}", headers=auth_headers).status_code == 200
        # 序列没了
        assert client.get(f"/series/{sid}", headers=auth_headers).status_code == 404
        # 检测记录还在
        recs = client.get("/history?limit=500", headers=auth_headers).json()["data"]
        assert any(r["id"] == did for r in recs)

    def test_trend_endpoint(self, client, auth_headers):
        sid = client.post("/series", json={"name": "s", "area_mu": 100},
                          headers=auth_headers).json()["series"]["id"]
        ids = [self._make_detection(client, auth_headers) for _ in range(3)]
        client.post(f"/series/{sid}/records", json={"records": [
            {"detection_id": ids[0], "t1_time": "2020-05", "t2_time": "2021-05"},
            {"detection_id": ids[1], "t1_time": "2021-05", "t2_time": "2022-05"},
            {"detection_id": ids[2], "t1_time": "2022-05", "t2_time": "2023-05"},
        ]}, headers=auth_headers)

        r = client.get(f"/series/{sid}/trend", headers=auth_headers).json()["trend"]
        assert r["interval_count"] == 3
        assert r["skipped"] == []
        assert r["fit"]["n"] == 3
        assert r["caveats"]
        assert r["summary"]["total_change_area_mu"] is not None

    def test_trend_reports_skipped(self, client, auth_headers):
        """没有日期的成员不能被静默丢弃，要在 skipped 里说明。"""
        sid = client.post("/series", json={"name": "s"},
                          headers=auth_headers).json()["series"]["id"]
        did = self._make_detection(client, auth_headers)
        # 绕过接口直接挂上（模拟历史遗留的无日期成员）
        from backend.app.models.database import SessionLocal
        from backend.app.models.detection import DetectionResultDB
        db = SessionLocal()
        rec = db.query(DetectionResultDB).filter(DetectionResultDB.id == did).first()
        rec.series_id = sid
        db.commit()
        db.close()

        r = client.get(f"/series/{sid}/trend", headers=auth_headers).json()["trend"]
        assert r["interval_count"] == 0
        assert len(r["skipped"]) == 1
        assert "日期" in r["skipped"][0]["reason"]

    def test_detect_can_join_series_directly(self, client, auth_headers):
        sid = client.post("/series", json={"name": "s"},
                          headers=auth_headers).json()["series"]["id"]
        from tests.conftest import _fake_png_bytes
        resp = client.post(
            "/detect",
            files=[("img1", ("t1.png", _fake_png_bytes(), "image/png")),
                   ("img2", ("t2.png", _fake_png_bytes(), "image/png"))],
            data={"model": "BIT", "threshold": 0.5, "series_id": sid,
                  "phase_index": 0, "t1_time": "2020-05", "t2_time": "2021-05"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        recs = client.get(f"/series/{sid}", headers=auth_headers).json()["records"]
        assert len(recs) == 1
        assert recs[0]["phase_index"] == 0

    def test_detect_rejects_other_users_series(self, client, auth_headers):
        sid = client.post("/series", json={"name": "s"},
                          headers=auth_headers).json()["series"]["id"]
        client.post("/register", json={"username": "other3", "password": "otherpass123"})
        tok = client.post("/login", json={"username": "other3",
                                          "password": "otherpass123"}).json()["token"]
        from tests.conftest import _fake_png_bytes
        resp = client.post(
            "/detect",
            files=[("img1", ("t1.png", _fake_png_bytes(), "image/png")),
                   ("img2", ("t2.png", _fake_png_bytes(), "image/png"))],
            data={"model": "BIT", "threshold": 0.5, "series_id": sid},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 404
