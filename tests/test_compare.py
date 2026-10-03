"""结果对比接口（GET /compare）与对比检测（POST /detect/compare）。

这个文件此前不存在 —— /compare 一直没有测试覆盖，而它自带一份结果序列化，
绕过了 history.py 的两条约定（重写结果 URL、时间转东八区），于是同一个系统里
对比页的时间比其他页面早 8 小时、图片在服务器换过域名后会裂。
"""
from datetime import timedelta

from backend.app.models.database import SessionLocal
from backend.app.models.detection import DetectionResultDB


def _compare(client, headers, rid):
    resp = client.get(f"/compare?id1={rid}&id2={rid}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["result1"]


class TestCompareSerialization:
    def test_time_is_converted_to_cst(self, client, auth_headers, detection_record):
        """库里存 UTC，对外必须转东八区（与 history 一致）。

        直接断言「等于 UTC+8」而不是「等于某个函数的结果」—— 后者是同义反复，
        那个函数改了它照样通过。
        """
        rid = detection_record["detection_id"]
        db = SessionLocal()
        try:
            rec = db.query(DetectionResultDB).filter(DetectionResultDB.id == rid).first()
            raw_utc = rec.created_at.strftime("%Y-%m-%d %H:%M:%S")
            expected_cst = (rec.created_at + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
        finally:
            db.close()

        got = _compare(client, auth_headers, rid)["time"]
        assert got != raw_utc, f"时间仍是 UTC：{got}"
        assert got == expected_cst, f"期望 {expected_cst}，实际 {got}"

    def test_stale_result_urls_are_rewritten(self, client, auth_headers, detection_record):
        """库里存的是检测当时的绝对地址，服务器换过域名/IP 后就是过期主机名。
        不重写就会裂图 —— series 与 history 都修过同类问题，compare 是第三处。"""
        rid = detection_record["detection_id"]
        db = SessionLocal()
        try:
            rec = db.query(DetectionResultDB).filter(DetectionResultDB.id == rid).first()
            rec.mask_url = "http://127.0.0.1:9999/results/stale_mask.png"
            rec.heat_url = None
            db.commit()
        finally:
            db.close()

        got = _compare(client, auth_headers, rid)
        assert got["mask"].endswith("/results/stale_mask.png")
        assert "127.0.0.1:9999" not in got["mask"], got["mask"]
        # 空值同样归一化为 ""，与其余端点一致
        assert got["heat"] == ""

    def test_rejects_other_users_record(self, client, detection_record):
        """用普通用户验，不能用管理员 —— compare.py 对 admin 有旁路
        （`if role != "admin"` 才校验归属），那是本文件既有的口径，
        不是这条测试要验的东西。"""
        rid = detection_record["detection_id"]
        client.post("/register", json={"username": "othercmp", "password": "otherpass123"})
        tok = client.post(
            "/login", json={"username": "othercmp", "password": "otherpass123"}
        ).json()["token"]
        resp = client.get(
            f"/compare?id1={rid}&id2={rid}", headers={"Authorization": f"Bearer {tok}"}
        )
        assert resp.status_code == 403, resp.text


class TestCompareDetectionPersistsScore:
    """/detect/compare 建的记录必须带概率图。

    它此前把 detect_change 返回的第一位丢掉了（写成 `_,`），于是对比检测建的
    记录在灾害定损 / Otsu / 重调阈值三条路径上全被拒 —— 而这三条都要求
    record.score_url。单张检测一直是对的，只有这条手抄的编排漏了。
    """

    def _compare_detect(self, client, auth_headers):
        from tests.conftest import _fake_png_bytes

        resp = client.post(
            "/detect/compare",
            files=[
                ("img1", ("t1.png", _fake_png_bytes(), "image/png")),
                ("img2", ("t2.png", _fake_png_bytes(), "image/png")),
            ],
            data={"models": '["BIT", "DIFF"]', "threshold": 0.5},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_record_has_score_url(self, client, auth_headers):
        body = self._compare_detect(client, auth_headers)
        rid = body["detection_id"]
        assert rid is not None

        db = SessionLocal()
        try:
            rec = db.query(DetectionResultDB).filter(DetectionResultDB.id == rid).first()
            assert rec.score_url, "对比检测的记录缺少 score_url"
            import os

            from backend.app.services.record_access import url_to_path

            assert os.path.exists(url_to_path(rec.score_url)), "概率图文件没落盘"
        finally:
            db.close()

    def test_record_can_be_assessed(self, client, auth_headers):
        """最终要的效果：这条记录能直接拿去做灾害定损。"""
        body = self._compare_detect(client, auth_headers)
        resp = client.post(
            "/disaster/assess",
            json={"detection_id": body["detection_id"], "area_mu": 100},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 200

    def test_each_model_returns_its_own_score(self, client, auth_headers):
        body = self._compare_detect(client, auth_headers)
        results = body["results"]
        assert set(results) == {"BIT", "DIFF"}
        for name, item in results.items():
            assert item["score"], f"{name} 的结果里缺 score"
