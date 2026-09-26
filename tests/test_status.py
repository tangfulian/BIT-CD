class TestStatus:
    def test_status_ok(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "model" in data
        assert "device" in data
        assert "uptime" in data
        assert "requests" in data
        assert "python_version" in data
        assert "pytorch_version" in data

    def test_status_no_auth_required(self, client):
        """Status endpoint should be publicly accessible."""
        resp = client.get("/status")
        assert resp.status_code == 200
