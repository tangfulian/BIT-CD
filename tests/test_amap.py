class TestAMapRegeo:
    def test_regeo_success(self, client):
        resp = client.post("/amap/regeo", json={"longitude": 126.63, "latitude": 45.75})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["province"] == "黑龙江省"
        assert "formatted_address" in data["data"]

    def test_regeo_invalid_longitude(self, client, monkeypatch):
        async def _regeo_with_validation(longitude, latitude):
            from fastapi import HTTPException
            if not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
                raise HTTPException(status_code=400, detail="经纬度错误")
            return {"province": "", "city": "", "district": "", "formatted_address": ""}
        monkeypatch.setattr("backend.app.routers.amap.reverse_geocode", _regeo_with_validation)
        monkeypatch.setattr("backend.app.services.amap_service.reverse_geocode", _regeo_with_validation)
        resp = client.post("/amap/regeo", json={"longitude": 200.0, "latitude": 45.75})
        assert resp.status_code == 400

    def test_regeo_invalid_latitude(self, client, monkeypatch):
        async def _regeo_with_validation(longitude, latitude):
            from fastapi import HTTPException
            if not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
                raise HTTPException(status_code=400, detail="经纬度错误")
            return {"province": "", "city": "", "district": "", "formatted_address": ""}
        monkeypatch.setattr("backend.app.routers.amap.reverse_geocode", _regeo_with_validation)
        monkeypatch.setattr("backend.app.services.amap_service.reverse_geocode", _regeo_with_validation)
        resp = client.post("/amap/regeo", json={"longitude": 100.0, "latitude": 100.0})
        assert resp.status_code == 400

    def test_regeo_rate_limit(self, client, monkeypatch):
        async def _rate_limited(longitude, latitude):
            from fastapi import HTTPException
            raise HTTPException(status_code=429, detail="请求过于频繁")
        monkeypatch.setattr("backend.app.routers.amap.reverse_geocode", _rate_limited)
        monkeypatch.setattr("backend.app.services.amap_service.reverse_geocode", _rate_limited)
        resp = client.post("/amap/regeo", json={"longitude": 100.0, "latitude": 45.0})
        assert resp.status_code == 429
