class TestAnnotation:
    def test_save_annotation(self, client, auth_headers, detection_record):
        det_id = detection_record["detection_id"]
        resp = client.post(
            f"/annotation/{det_id}",
            json={"annotation_data": "base64fakeannotationdata"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 200

    def test_get_annotation(self, client, auth_headers, detection_record):
        det_id = detection_record["detection_id"]
        # Save annotation first
        client.post(
            f"/annotation/{det_id}",
            json={"annotation_data": "base64fakeannotationdata"},
            headers=auth_headers,
        )
        resp = client.get(f"/annotation/{det_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["annotation_data"] == "base64fakeannotationdata"

    def test_get_annotation_none(self, client, auth_headers):
        # Create detection first
        resp = client.post(
            "/detect",
            files=[
                ("img1", ("t1.png", _fake_png(), "image/png")),
                ("img2", ("t2.png", _fake_png(), "image/png")),
            ],
            data={"model": "BIT", "threshold": 0.5},
            headers=auth_headers,
        )
        det_id = resp.json()["detection_id"]
        r = client.get(f"/annotation/{det_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["annotation_data"] is None

    def test_annotation_detection_not_found(self, client, auth_headers):
        resp = client.post(
            "/annotation/99999",
            json={"annotation_data": "data"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_annotation_unauthorized(self, client, auth_headers):
        # Register another user
        client.post("/register", json={"username": "other", "password": "testpass123"})
        resp2 = client.post("/login", json={"username": "other", "password": "testpass123"})
        other_headers = {"Authorization": f"Bearer {resp2.json()['token']}"}

        # Create detection as testuser (via auth_headers)
        det = client.post(
            "/detect",
            files=[
                ("img1", ("t1.png", _fake_png(), "image/png")),
                ("img2", ("t2.png", _fake_png(), "image/png")),
            ],
            data={"model": "BIT", "threshold": 0.5},
            headers=auth_headers,
        )
        det_id = det.json()["detection_id"]

        # other user tries to annotate testuser's detection
        resp = client.post(
            f"/annotation/{det_id}",
            json={"annotation_data": "stolen"},
            headers=other_headers,
        )
        assert resp.status_code == 403


def _fake_png():
    import io
    import numpy as np
    from PIL import Image
    arr = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
