class TestHistory:
    def test_history_empty(self, client, auth_headers):
        resp = client.get("/history", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 200
        assert resp.json()["data"] == []

    def test_history_requires_auth(self, client):
        resp = client.get("/history")
        assert resp.status_code == 401

    def test_history_with_data(self, client, auth_headers, monkeypatch):
        from backend.app.routers import detect as detect_router
        from backend.app.routers import history as history_router

        # Insert a detection record through the detect endpoint (mocked)
        import io

        import numpy as np
        from PIL import Image

        def _fake_img():
            arr = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
            img = Image.fromarray(arr)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            return buf

        def mock_detect_change(img1, img2, threshold, model_type, unique_id):
            sm = np.zeros((256, 256), dtype=np.float32)
            sm[50:100, 50:100] = 0.9
            mask = (sm > threshold).astype(np.uint8) * 255
            heatmap = np.zeros((256, 256, 3), dtype=np.uint8)
            fusion = np.zeros((256, 256, 3), dtype=np.uint8)
            stats = {"total_pixel": 65536, "change_pixel": 2500, "ratio": 3.81, "threshold": threshold}
            return sm, mask, heatmap, fusion, stats

        monkeypatch.setattr(detect_router, "detect_change", mock_detect_change)

        # Create 2 detections
        for _ in range(2):
            client.post(
                "/detect",
                files=[
                    ("img1", ("t1.png", _fake_img(), "image/png")),
                    ("img2", ("t2.png", _fake_img(), "image/png")),
                ],
                data={"model": "BIT", "threshold": 0.5},
                headers=auth_headers,
            )

        resp = client.get("/history", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        assert data[0]["model"] == "BIT"
        assert "mask" in data[0]
        assert "time" in data[0]


class TestCompare:
    def test_compare_requires_auth(self, client):
        resp = client.get("/compare?id1=1&id2=2")
        assert resp.status_code == 401

    def test_compare_not_found(self, client, auth_headers):
        resp = client.get("/compare?id1=999&id2=998", headers=auth_headers)
        assert resp.status_code == 404
