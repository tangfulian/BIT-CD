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
        from backend.app.routers import detect as detect_router

        def mock_detect_change(img1, img2, threshold, model_type, unique_id):
            sm = _fake_score_map()
            mask = (sm > threshold).astype(np.uint8) * 255
            heatmap = np.zeros((256, 256, 3), dtype=np.uint8)
            fusion = np.zeros((256, 256, 3), dtype=np.uint8)
            stats = {"total_pixel": 65536, "change_pixel": 2500, "ratio": 3.81, "threshold": threshold}
            return sm, mask, heatmap, fusion, stats

        monkeypatch.setattr(detect_router, "detect_change", mock_detect_change)

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
        assert data["stats"]["ratio"] == 3.81

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
