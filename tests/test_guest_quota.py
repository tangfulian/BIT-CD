"""游客免费额度：服务端计数。

额度此前只活在前端 localStorage —— 清缓存就归零，直接打接口完全不受约束。
这里验的是服务端那一侧：按 IP 按天，第四次被拒，失败不扣次数。
"""

import io

import numpy as np
from PIL import Image

from backend.app.models.database import SessionLocal
from backend.app.models.guest_usage import GuestUsageDB
from backend.app.services import guest_quota


def _png():
    arr = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    buf.seek(0)
    return buf


def _detect(client, headers=None):
    return client.post(
        "/detect",
        files=[
            ("img1", ("t1.png", _png(), "image/png")),
            ("img2", ("t2.png", _png(), "image/png")),
        ],
        data={"model": "BIT", "threshold": 0.5},
        headers=headers or {},
    )


def _used() -> int:
    db = SessionLocal()
    try:
        rows = db.query(GuestUsageDB).all()
        return sum(r.used for r in rows)
    finally:
        db.close()


class TestGuestQuota:
    def test_fourth_guest_detection_is_rejected(self, client):
        for i in range(3):
            resp = _detect(client)
            assert resp.status_code == 200, f"第 {i + 1} 次不该被拒"
            assert resp.json()["guest_remaining"] == 2 - i

        resp = _detect(client)
        assert resp.status_code == 429
        assert "登录" in resp.json()["detail"]

    def test_logged_in_user_is_not_counted(self, client, auth_headers):
        for _ in range(4):
            assert _detect(client, auth_headers).status_code == 200
        assert _used() == 0
        assert "guest_remaining" not in _detect(client, auth_headers).json()

    def test_failed_detection_does_not_consume(self, client):
        resp = client.post(
            "/detect",
            files=[
                ("img1", ("t1.png", b"not an image", "image/png")),
                ("img2", ("t2.png", b"not an image", "image/png")),
            ],
            data={"model": "BIT", "threshold": 0.5},
        )
        assert resp.status_code == 400
        assert _used() == 0

    def test_quota_resets_next_day(self, client, monkeypatch):
        for _ in range(3):
            assert _detect(client).status_code == 200
        assert _detect(client).status_code == 429

        # 把计数器挪到「昨天」，模拟跨天
        from backend.app.services import guest_quota as gq

        monkeypatch.setattr(gq, "_today", lambda: "2099-01-01")
        assert _detect(client).status_code == 200

    def test_zero_means_unlimited(self, client, monkeypatch):
        monkeypatch.setattr(guest_quota, "GUEST_DAILY_QUOTA", 0)
        for _ in range(5):
            assert _detect(client).status_code == 200


class TestCompareCounts:
    def test_compare_respects_the_same_quota(self, client):
        for _ in range(3):
            assert _detect(client).status_code == 200

        resp = client.post(
            "/detect/compare",
            files=[
                ("img1", ("t1.png", _png(), "image/png")),
                ("img2", ("t2.png", _png(), "image/png")),
            ],
            data={"models": '["BIT","DIFF"]', "threshold": 0.5},
        )
        # 走另一个接口不该绕过额度
        assert resp.status_code == 429
