"""GitHub 第三方登录。

不真的访问 GitHub —— `_exchange_code` 被替换成假函数，返回一个固定的
GitHub 用户。真正外部依赖的只有这一步；state 校验、找/建账号、签发令牌
这些逻辑都在本地，全部真实执行。
"""

from urllib.parse import parse_qs, urlparse

import pytest

from backend.app.core import config as cfg
from backend.app.models.database import SessionLocal
from backend.app.models.oauth import OAuthAccountDB
from backend.app.models.user import UserDB


@pytest.fixture
def github_enabled(monkeypatch):
    monkeypatch.setattr(cfg, "GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(cfg, "GITHUB_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(cfg, "GITHUB_OAUTH_ENABLED", True)
    monkeypatch.setattr(cfg, "GITHUB_REDIRECT_URI", "")


def _fake_github_user(login="octocat", uid=583231):
    return {"id": uid, "login": login, "name": "The Octocat", "avatar_url": ""}


def _start(client):
    """走一遍 /authorize，拿回 GitHub 回调时该带上的 state。"""
    resp = client.get("/auth/github/authorize", follow_redirects=False)
    assert resp.status_code == 302
    query = parse_qs(urlparse(resp.headers["location"]).query)
    return query["state"][0], query


def _callback(client, state, code="the-code"):
    resp = client.get(
        "/auth/github/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    return urlparse(resp.headers["location"]).fragment


class TestProviders:
    def test_disabled_when_not_configured(self, client, monkeypatch):
        # 不能依赖「本地没配 .env」—— 开发机上配了真凭据时这条会假失败
        monkeypatch.setattr(cfg, "GITHUB_OAUTH_ENABLED", False)
        resp = client.get("/auth/providers")
        assert resp.status_code == 200
        assert resp.json()["data"]["github"] is False

    def test_enabled_when_configured(self, client, github_enabled):
        assert client.get("/auth/providers").json()["data"]["github"] is True

    def test_authorize_refuses_when_not_configured(self, client, monkeypatch):
        monkeypatch.setattr(cfg, "GITHUB_OAUTH_ENABLED", False)
        resp = client.get("/auth/github/authorize", follow_redirects=False)
        assert resp.status_code == 503


class TestAuthorize:
    def test_redirects_to_github_with_state(self, client, github_enabled):
        state, query = _start(client)
        assert query["client_id"][0] == "test-client-id"
        assert query["redirect_uri"][0].endswith("/auth/github/callback")
        assert state
        assert "oauth_state" in client.cookies

    def test_state_is_not_reused_verbatim(self, client, github_enabled):
        first, _ = _start(client)
        second, _ = _start(client)
        assert first != second


class TestCallbackStateChecks:
    def test_missing_cookie_is_rejected(self, client, github_enabled):
        """伪造的 state 即使签名合法，没有对应 cookie 也要拒 —— 防 CSRF。"""
        from backend.app.routers.oauth import _make_state

        _, forged = _make_state()
        client.cookies.clear()
        fragment = _callback(client, forged)
        assert fragment == "oauth_error=state"

    def test_garbage_state_is_rejected(self, client, github_enabled):
        _start(client)
        fragment = _callback(client, "not-a-jwt")
        assert fragment == "oauth_error=state"

    def test_provider_error_is_reported(self, client, github_enabled):
        resp = client.get(
            "/auth/github/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )
        assert urlparse(resp.headers["location"]).fragment == "oauth_error=denied"


class TestLogin:
    def test_first_login_creates_account(self, client, github_enabled, monkeypatch):
        monkeypatch.setattr(
            "backend.app.routers.oauth._exchange_code",
            lambda code, uri: _fake_github_user(),
        )
        state, _ = _start(client)
        fragment = _callback(client, state)

        assert fragment.startswith("oauth_token=")
        token = fragment[len("oauth_token="):]

        # 签出来的令牌要真的能用
        resp = client.get("/plots", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

        db = SessionLocal()
        try:
            user = db.query(UserDB).filter(UserDB.username == "octocat").first()
            assert user is not None
            link = db.query(OAuthAccountDB).filter_by(provider="github").first()
            assert link is not None and link.user_id == user.id
            assert link.provider_uid == "583231"
        finally:
            db.close()

    def test_second_login_reuses_account(self, client, github_enabled, monkeypatch):
        monkeypatch.setattr(
            "backend.app.routers.oauth._exchange_code",
            lambda code, uri: _fake_github_user(),
        )
        _callback(client, _start(client)[0])
        _callback(client, _start(client)[0])

        db = SessionLocal()
        try:
            assert db.query(UserDB).filter(UserDB.username == "octocat").count() == 1
            assert db.query(OAuthAccountDB).count() == 1
        finally:
            db.close()

    def test_username_collision_creates_separate_account(
        self, client, github_enabled, monkeypatch
    ):
        """本地已有 octocat 时，GitHub 上的 octocat 不能登进这个账号。"""
        client.post("/register", json={"username": "octocat", "password": "testpass123"})
        monkeypatch.setattr(
            "backend.app.routers.oauth._exchange_code",
            lambda code, uri: _fake_github_user(),
        )
        _callback(client, _start(client)[0])

        db = SessionLocal()
        try:
            # admin 是 init_db 建的，不计入
            names = sorted(u.username for u in db.query(UserDB).all() if u.username != "admin")
            assert names == ["octocat", "octocat-gh1"]
        finally:
            db.close()

    def test_password_login_does_not_work_for_oauth_account(
        self, client, github_enabled, monkeypatch
    ):
        monkeypatch.setattr(
            "backend.app.routers.oauth._exchange_code",
            lambda code, uri: _fake_github_user(),
        )
        _callback(client, _start(client)[0])

        # 随机口令被丢弃了，任何人拿任意密码都不该登进去
        for pwd in ("", "testpass123", "octocat"):
            resp = client.post("/login", json={"username": "octocat", "password": pwd})
            assert resp.status_code in (401, 422)

    def test_disabled_account_is_refused(self, client, github_enabled, monkeypatch):
        monkeypatch.setattr(
            "backend.app.routers.oauth._exchange_code",
            lambda code, uri: _fake_github_user(),
        )
        _callback(client, _start(client)[0])

        db = SessionLocal()
        try:
            user = db.query(UserDB).filter(UserDB.username == "octocat").first()
            user.disabled = 1
            db.commit()
        finally:
            db.close()

        fragment = _callback(client, _start(client)[0])
        assert fragment == "oauth_error=disabled"

    def test_github_failure_does_not_leak_details(
        self, client, github_enabled, monkeypatch
    ):
        from backend.app.routers.oauth import _OAuthError

        def _boom(code, uri):
            raise _OAuthError("token endpoint said: bad_verification_code")

        monkeypatch.setattr("backend.app.routers.oauth._exchange_code", _boom)
        fragment = _callback(client, _start(client)[0])
        # 只回一个错误码，不把上游的原始错误信息带给浏览器
        assert fragment == "oauth_error=github"
