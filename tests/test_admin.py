class TestAdminUsers:
    def test_list_users_as_admin(self, client, admin_headers):
        resp = client.get("/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        users = data["data"]
        assert len(users) >= 1
        assert users[0]["username"] is not None
        assert "detection_count" in users[0]

    def test_list_users_as_normal_user(self, client, auth_headers):
        resp = client.get("/admin/users", headers=auth_headers)
        assert resp.status_code == 403

    def test_list_users_no_auth(self, client):
        resp = client.get("/admin/users")
        assert resp.status_code == 401


class TestAdminToggleStatus:
    def test_toggle_disable_user(self, client, admin_headers, auth_headers):
        # First get the user ID of the test user from auth_headers fixture
        # Register another user to toggle
        client.post("/register", json={"username": "victim", "password": "testpass123"})
        resp = client.get("/admin/users", headers=admin_headers)
        victim = [u for u in resp.json()["data"] if u["username"] == "victim"][0]

        toggle = client.put(f"/admin/users/{victim['id']}/toggle-status", headers=admin_headers)
        assert toggle.status_code == 200
        assert toggle.json()["disabled"] is True

    def test_toggle_enable_user(self, client, admin_headers):
        client.post("/register", json={"username": "victim2", "password": "testpass123"})
        resp = client.get("/admin/users", headers=admin_headers)
        victim = [u for u in resp.json()["data"] if u["username"] == "victim2"][0]
        # First disable
        client.put(f"/admin/users/{victim['id']}/toggle-status", headers=admin_headers)
        # Then enable back
        toggle = client.put(f"/admin/users/{victim['id']}/toggle-status", headers=admin_headers)
        assert toggle.status_code == 200
        assert toggle.json()["disabled"] is False

    def test_toggle_self(self, client, admin_headers):
        resp = client.get("/admin/users", headers=admin_headers)
        myself = [u for u in resp.json()["data"] if u["username"] == "adminuser"][0]
        toggle = client.put(f"/admin/users/{myself['id']}/toggle-status", headers=admin_headers)
        assert toggle.status_code == 400

    def test_toggle_not_found(self, client, admin_headers):
        resp = client.put("/admin/users/99999/toggle-status", headers=admin_headers)
        assert resp.status_code == 404

    def test_toggle_no_auth(self, client):
        resp = client.put("/admin/users/1/toggle-status")
        assert resp.status_code == 401


class TestAdminResetPassword:
    def test_reset_password_success(self, client, admin_headers):
        # Create a new user
        client.post("/register", json={"username": "resetme", "password": "testpass123"})
        resp = client.get("/admin/users", headers=admin_headers)
        victim = [u for u in resp.json()["data"] if u["username"] == "resetme"][0]

        r = client.put(f"/admin/users/{victim['id']}/password", headers=admin_headers)
        assert r.status_code == 200
        assert "密码已重置" in r.json()["msg"]

        # 重置后应能用 USER_RESET_PASSWORD 登录（测试环境中由 conftest 固定为 testreset123）
        login_resp = client.post("/login", json={"username": "resetme", "password": "testreset123"})
        assert login_resp.status_code == 200

    def test_reset_not_found(self, client, admin_headers):
        resp = client.put("/admin/users/99999/password", headers=admin_headers)
        assert resp.status_code == 404


class TestAdminDelete:
    def test_delete_user_success(self, client, admin_headers):
        client.post("/register", json={"username": "deleteme", "password": "testpass123"})
        resp = client.get("/admin/users", headers=admin_headers)
        victim = [u for u in resp.json()["data"] if u["username"] == "deleteme"][0]

        r = client.delete(f"/admin/users/{victim['id']}", headers=admin_headers)
        assert r.status_code == 200
        assert "已删除" in r.json()["msg"]

        # Verify user gone
        resp2 = client.get("/admin/users", headers=admin_headers)
        assert not any(u["username"] == "deleteme" for u in resp2.json()["data"])

    def test_delete_self(self, client, admin_headers):
        resp = client.get("/admin/users", headers=admin_headers)
        myself = [u for u in resp.json()["data"] if u["username"] == "adminuser"][0]
        r = client.delete(f"/admin/users/{myself['id']}", headers=admin_headers)
        assert r.status_code == 400

    def test_delete_not_found(self, client, admin_headers):
        resp = client.delete("/admin/users/99999", headers=admin_headers)
        assert resp.status_code == 404

    def test_delete_non_admin(self, client, auth_headers):
        resp = client.delete("/admin/users/1", headers=auth_headers)
        assert resp.status_code == 403
