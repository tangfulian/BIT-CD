class TestAIChat:
    def test_chat_success(self, client, auth_headers):
        resp = client.post("/ai/chat", json={"user_input": "什么是黑土地保护？", "history": []},
                           headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "AI模拟回复" in data["reply"]

    def test_chat_with_history(self, client, auth_headers):
        resp = client.post(
            "/ai/chat",
            json={
                "user_input": "继续解释",
                "history": [{"role": "user", "content": "什么是黑土地？"}, {"role": "assistant", "content": "黑土地是..."}],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 200

    def test_chat_service_error(self, client, auth_headers, monkeypatch):
        def _failing_chat(user_input, history, system_prompt):
            raise Exception("AI服务崩溃")
        monkeypatch.setattr("backend.app.routers.ai.chat", _failing_chat)
        monkeypatch.setattr("backend.app.services.ai_service.chat", _failing_chat)
        resp = client.post("/ai/chat", json={"user_input": "测试", "history": []}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 500
        assert "异常" in data["reply"]


class TestAIAnalysis:
    def test_analysis_success(self, client, auth_headers):
        resp = client.post(
            "/ai/analysis-detect-result",
            json={
                "change_area_ratio": 3.81,
                "change_pixel": 2500,
                "total_pixel": 65536,
                "threshold": 0.5,
                "change_type": "耕地退化",
                "t1_time": "2020-06",
                "t2_time": "2025-06",
                "province": "黑龙江省",
                "city": "哈尔滨市",
                "lat_lng": "126.63,45.75",
                "area": "100.5",
                "land_type": "耕地",
                "crop_type": "玉米",
                "data_source": "GF-1",
                "location": "黑龙江省哈尔滨市",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "AI模拟回复" in data["analysis"]

    def test_analysis_service_error(self, client, auth_headers, monkeypatch):
        def _failing_chat(user_input, history, system_prompt):
            raise Exception("AI分析崩溃")
        monkeypatch.setattr("backend.app.routers.ai.chat", _failing_chat)
        monkeypatch.setattr("backend.app.services.ai_service.chat", _failing_chat)
        resp = client.post(
            "/ai/analysis-detect-result",
            json={
                "change_area_ratio": 3.81,
                "change_pixel": 2500,
                "total_pixel": 65536,
                "threshold": 0.5,
                "change_type": "耕地退化",
                "t1_time": "2020-06",
                "t2_time": "2025-06",
                "province": "黑龙江省",
                "city": "哈尔滨市",
                "lat_lng": "126.63,45.75",
                "area": "100",
                "land_type": "耕地",
                "crop_type": "玉米",
                "data_source": "GF-1",
                "location": "黑龙江省哈尔滨市",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 500
