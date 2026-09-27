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
        # /detect 的编排已下沉到 detection_service，它按**模块属性**调用
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
