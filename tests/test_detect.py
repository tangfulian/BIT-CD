import io

import numpy as np
from PIL import Image


def _fake_image():
    """Generate a 256x256 RGB PNG as bytes."""
    arr = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _fake_score_map():
    """Return a 256x256 numpy score map with a patch of 'change'."""
    sm = np.zeros((256, 256), dtype=np.float32)
    sm[100:150, 100:150] = 0.8  # a patch of high change probability
    return sm


class TestDetect:
    def test_detect_bit_model(self, client, auth_headers, monkeypatch):
        # /detect 的编排已下沉到 detection_pipeline，它按**模块属性**调用
        # detect_service.detect_change。所以桩必须打在 detect_service 这个
        # 命名空间上；打在 routers.detect 上对 /detect 已经无效（那个名字
        # 现在只被 /detect/compare 用）。
        from backend.app.services import detect_service

        def mock_detect_change(img1, img2, threshold, model_type, unique_id):
            sm = _fake_score_map()
            mask = (sm > threshold).astype(np.uint8) * 255
            heatmap = np.zeros((256, 256, 3), dtype=np.uint8)
            fusion = np.zeros((256, 256, 3), dtype=np.uint8)
            # 数值刻意与 conftest 的全局假桩（ratio 3.81）不同：这一处打桩
            # 若再次静默失效，请求会落到全局假桩并返回 3.81，下面的断言
            # 立刻失败。这是给「from X import y 导致桩失效、但测试照样通过」
            # 那个坑留的探针。
            stats = {"total_pixel": 65536, "change_pixel": 1234, "ratio": 7.77, "threshold": threshold}
            return sm, mask, heatmap, fusion, stats

        monkeypatch.setattr(detect_service, "detect_change", mock_detect_change)

        img1 = _fake_image()
        img2 = _fake_image()

        resp = client.post(
            "/detect",
            files=[
                ("img1", ("t1.png", img1, "image/png")),
                ("img2", ("t2.png", img2, "image/png")),
            ],
            data={
                "model": "BIT",
                "threshold": 0.5,
                "lat_lng": "126.63,45.75",
                "location": "黑龙江省哈尔滨市",
                "change_type": "耕地退化",
                "t1_time": "2020-06",
                "t2_time": "2025-06",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["model"] == "BIT"
        assert data["detection_id"] is not None
        assert "mask" in data
        assert "heat" in data
        assert "fusion" in data
        assert data["stats"]["ratio"] == 7.77

    def test_detect_requires_auth(self, client):
        resp = client.post("/detect", files=[], data={})
        assert resp.status_code in [401, 422]

    def test_detect_invalid_model(self, client, auth_headers):
        resp = client.post(
            "/detect",
            files=[
                ("img1", ("t1.png", _fake_image(), "image/png")),
                ("img2", ("t2.png", _fake_image(), "image/png")),
            ],
            data={"model": "INVALID_MODEL", "threshold": 0.5},
            headers=auth_headers,
        )
        assert resp.status_code == 400


class TestRecommendThreshold:
    def test_recommend_success(self, client):
        img1 = _fake_image()
        img2 = _fake_image()
        resp = client.post(
            "/recommend-threshold",
            files=[
                ("img1", ("t1.png", img1, "image/png")),
                ("img2", ("t2.png", img2, "image/png")),
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert 0.1 <= data["threshold"] <= 0.9


class TestDetectCache:
    """缓存键与元数据的边界。

    影像 + 模型 + 阈值决定像素，元数据（地名 / 变化类型 / 前后时相 /
    序列归属）只是描述 —— 但描述也是用户填的，不能被上一轮的值顶掉。
    """

    def _post(self, client, headers, b1, b2, **data):
        payload = {"model": "BIT", "threshold": 0.5}
        payload.update(data)
        return client.post(
            "/detect",
            files=[
                ("img1", ("t1.png", io.BytesIO(b1), "image/png")),
                ("img2", ("t2.png", io.BytesIO(b2), "image/png")),
            ],
            data=payload,
            headers=headers,
        )

    def test_same_input_reuses_the_same_record(self, client, auth_headers):
        b1 = _fake_image().getvalue()
        b2 = _fake_image().getvalue()
        a = self._post(client, auth_headers, b1, b2, location="甲市")
        b = self._post(client, auth_headers, b1, b2, location="甲市")
        assert a.status_code == 200 and b.status_code == 200
        assert a.json()["detection_id"] == b.json()["detection_id"]

    def test_metadata_is_refreshed_on_cache_hit(self, client, auth_headers):
        from backend.app.models.database import SessionLocal
        from backend.app.models.detection import DetectionResultDB

        b1 = _fake_image().getvalue()
        b2 = _fake_image().getvalue()
        first = self._post(
            client, auth_headers, b1, b2,
            location="甲市", change_type="耕地退化", t1_time="2021-05",
        )
        did = first.json()["detection_id"]

        second = self._post(
            client, auth_headers, b1, b2,
            location="乙市", change_type="风蚀沙化", t1_time="2022-06",
        )
        # 像素完全一样，不该重新推理
        assert second.json()["detection_id"] == did

        db = SessionLocal()
        try:
            rec = db.query(DetectionResultDB).filter(DetectionResultDB.id == did).first()
            # 但记录上的描述必须是这次填的，否则历史里会挂着上一个地块的县名
            assert rec.location == "乙市"
            assert rec.change_type == "风蚀沙化"
            assert rec.t1_time == "2022-06"
        finally:
            db.close()

    def test_different_series_gets_its_own_record(self, client, auth_headers):
        b1 = _fake_image().getvalue()
        b2 = _fake_image().getvalue()

        def make_series(name):
            resp = client.post(
                "/series", json={"name": name, "location": "甲市"}, headers=auth_headers
            )
            return resp.json()["series"]["id"]

        s1, s2 = make_series("序列一"), make_series("序列二")

        a = self._post(client, auth_headers, b1, b2, series_id=s1)
        b = self._post(client, auth_headers, b1, b2, series_id=s2)
        assert a.status_code == 200 and b.status_code == 200
        # 同一对影像挂到另一个序列上是另一条记录 —— 否则新序列里空空如也
        assert a.json()["detection_id"] != b.json()["detection_id"]
