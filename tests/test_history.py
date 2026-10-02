class TestHistory:
    def test_history_empty(self, client, auth_headers):
        resp = client.get("/history", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 200
        assert resp.json()["data"] == []

    def test_history_requires_auth(self, client):
        resp = client.get("/history")
        assert resp.status_code == 401

    def test_history_with_data(self, client, auth_headers):
        # 检测本身由 conftest 的 autouse 夹具 mock_detect_service 打桩，这里不必再打。
        # 此处原先还留着一份自己的桩，打在 detect_router.detect_change 上 ——
        # /detect 的编排下沉到 detection_pipeline 之后，那个名字已经不被调用了，
        # 而那份桩的返回值又与全局假桩一模一样，所以它失效了也看不出来。

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
