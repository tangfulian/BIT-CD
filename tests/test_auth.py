class TestRegister:
    def test_register_success(self, client):
        resp = client.post("/register", json={"username": "newuser", "password": "pass12345"})
        assert resp.status_code == 200
        assert resp.json()["code"] == 200
        assert resp.json()["msg"] == "注册成功"

    def test_register_duplicate(self, client):
        client.post("/register", json={"username": "dup", "password": "pass12345"})
        resp = client.post("/register", json={"username": "dup", "password": "pass12345"})
        assert resp.status_code == 400
        assert "已存在" in resp.json()["detail"]

    def test_register_short_password(self, client):
        resp = client.post("/register", json={"username": "short", "password": "123"})
        assert resp.status_code == 422  # Pydantic schema min_length=8 rejects before router


class TestLogin:
    def test_login_success(self, client):
        client.post("/register", json={"username": "loginuser", "password": "pass12345"})
        resp = client.post("/login", json={"username": "loginuser", "password": "pass12345"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "token" in data
        assert data["username"] == "loginuser"
        assert data["role"] == "user"

    def test_login_wrong_password(self, client):
        client.post("/register", json={"username": "wrongpw", "password": "pass12345"})
        resp = client.post("/login", json={"username": "wrongpw", "password": "badpass12"})
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/login", json={"username": "ghost", "password": "pass12345"})
        assert resp.status_code == 401

    def test_login_disabled_user(self, client):
        from backend.app.core.security import hash_password
        from backend.app.models.database import SessionLocal
        from backend.app.models.user import UserDB

        db = SessionLocal()
        db.add(UserDB(username="disabled", password_hash=hash_password("pass12345"), disabled=1))
        db.commit()
        db.close()

        resp = client.post("/login", json={"username": "disabled", "password": "pass12345"})
        assert resp.status_code == 403
        assert "禁用" in resp.json()["detail"]
