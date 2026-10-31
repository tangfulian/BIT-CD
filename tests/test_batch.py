"""批量检测的服务端任务队列。

执行器在测试里是关掉的（conftest 设 BATCH_WORKER=0），所以这里直接调
`_run_job` 把任务跑完 —— 测的是「任务怎么建、怎么跑、怎么取消、怎么隔离」，
不是线程调度本身。
"""

import io

import numpy as np
from PIL import Image

from backend.app.models.batch import BatchJobDB, BatchJobItemDB
from backend.app.models.database import SessionLocal


def _png():
    arr = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def _create(client, headers, pairs=2, model="BIT"):
    files = []
    for _ in range(pairs):
        files.append(("img1", ("t1.png", io.BytesIO(_png()), "image/png")))
        files.append(("img2", ("t2.png", io.BytesIO(_png()), "image/png")))
    return client.post(
        "/batch",
        files=files,
        data={"model": model, "threshold": 0.5},
        headers=headers,
    )


class TestCreate:
    def test_creates_queued_job(self, client, auth_headers):
        resp = _create(client, auth_headers, pairs=3)
        assert resp.status_code == 200
        job = resp.json()["data"]
        assert job["status"] == "queued"
        assert job["total"] == 3
        assert job["done"] == 0

    def test_requires_login(self, client):
        assert _create(client, {}, pairs=1).status_code == 401

    def test_rejects_mismatched_pairs(self, client, auth_headers):
        files = [
            ("img1", ("t1.png", io.BytesIO(_png()), "image/png")),
            ("img2", ("t2.png", io.BytesIO(_png()), "image/png")),
            ("img2", ("t2b.png", io.BytesIO(_png()), "image/png")),
        ]
        resp = client.post(
            "/batch", files=files, data={"model": "BIT", "threshold": 0.5},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "配对" in resp.json()["detail"]


class TestRun:
    def test_run_marks_items_done(self, client, auth_headers):
        from backend.app.services.batch_runner import _run_job

        job_id = _create(client, auth_headers, pairs=2).json()["data"]["id"]
        _run_job(job_id)

        data = client.get(f"/batch/{job_id}", headers=auth_headers).json()["data"]
        assert data["status"] == "done"
        assert data["done"] == 2 and data["failed"] == 0
        assert all(it["status"] == "done" for it in data["items"])
        assert all(it["detection_id"] for it in data["items"])

    def test_one_bad_pair_does_not_kill_the_batch(self, client, auth_headers):
        """一组坏图不该让整批失败 —— 记下来接着跑下一组。"""
        from backend.app.services.batch_runner import _run_job

        job = client.post(
            "/batch",
            files=[
                ("img1", ("a.png", io.BytesIO(b"not an image"), "image/png")),
                ("img2", ("b.png", io.BytesIO(b"not an image"), "image/png")),
                ("img1", ("c.png", io.BytesIO(_png()), "image/png")),
                ("img2", ("d.png", io.BytesIO(_png()), "image/png")),
            ],
            data={"model": "BIT", "threshold": 0.5},
            headers=auth_headers,
        ).json()["data"]

        _run_job(job["id"])
        data = client.get(f"/batch/{job['id']}", headers=auth_headers).json()["data"]
        assert data["status"] == "done"
        assert data["done"] == 1 and data["failed"] == 1
        statuses = [it["status"] for it in data["items"]]
        assert statuses == ["failed", "done"]


class TestIsolation:
    def test_other_users_cannot_see_the_job(self, client, auth_headers):
        job_id = _create(client, auth_headers, pairs=1).json()["data"]["id"]

        client.post("/register", json={"username": "other", "password": "testpass123"})
        token = client.post(
            "/login", json={"username": "other", "password": "testpass123"}
        ).json()["token"]
        other = {"Authorization": f"Bearer {token}"}

        assert client.get(f"/batch/{job_id}", headers=other).status_code == 404
        assert client.post(f"/batch/{job_id}/cancel", headers=other).status_code == 404

    def test_list_only_returns_own_jobs(self, client, auth_headers):
        _create(client, auth_headers, pairs=1)
        ids = [j["id"] for j in client.get("/batch", headers=auth_headers).json()["data"]]
        assert ids
        assert len(ids) == 1


class TestCancel:
    def test_cancel_marks_job_and_stops_worker(self, client, auth_headers):
        from backend.app.services.batch_runner import _run_job

        job_id = _create(client, auth_headers, pairs=3).json()["data"]["id"]
        resp = client.post(f"/batch/{job_id}/cancel", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"

        # worker 领到的是已取消的任务 → 一条都不该跑
        _run_job(job_id)
        db = SessionLocal()
        try:
            job = db.query(BatchJobDB).filter(BatchJobDB.id == job_id).first()
            items = db.query(BatchJobItemDB).filter(BatchJobItemDB.job_id == job_id).all()
            assert job.status == "cancelled"
            assert all(it.status == "queued" for it in items)
        finally:
            db.close()

    def test_cancel_after_done_is_rejected(self, client, auth_headers):
        from backend.app.services.batch_runner import _run_job

        job_id = _create(client, auth_headers, pairs=1).json()["data"]["id"]
        _run_job(job_id)
        assert client.post(f"/batch/{job_id}/cancel", headers=auth_headers).status_code == 400


class TestRestartRecovery:
    def test_stuck_running_jobs_are_requeued(self, client, auth_headers):
        """进程重启时停在 running 的任务必须退回队列，否则进度条永远不动。"""
        from backend.app.services.batch_runner import reset_stuck_jobs

        job_id = _create(client, auth_headers, pairs=1).json()["data"]["id"]
        db = SessionLocal()
        try:
            db.query(BatchJobDB).filter(BatchJobDB.id == job_id).update(
                {"status": "running"}, synchronize_session=False
            )
            db.commit()
        finally:
            db.close()

        assert reset_stuck_jobs() >= 1

        data = client.get(f"/batch/{job_id}", headers=auth_headers).json()["data"]
        assert data["status"] == "queued"
