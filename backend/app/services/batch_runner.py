"""批量检测的后台执行器。

一个常驻线程，从 batch_jobs 里领 queued 的任务逐条跑。为什么要线程而不是
任务队列服务：这台机器上就一个 uvicorn 进程、一个 CPU，推理本身是串行的，
再引入 Celery/Redis 只是多一层部署负担。

三条与「简陋」划清界限的地方：

1. **领任务是原子的**（条件 UPDATE），不是先查后改 —— 两个 worker 同时启动
   也不会把同一批跑两遍。
2. **进程重启后不丢任务**：启动时把停在 running 的任务退回 queued 重跑。
   重跑是安全的，因为单张检测本身按影像哈希去重。
3. **取消是协作式的**：worker 每处理完一条看一眼状态，不硬杀线程 ——
   半路杀掉的线程会把 detection 记录和结果文件留在不一致的中间态。
"""

import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import text

from backend.app.models.batch import BatchJobDB, BatchJobItemDB
from backend.app.models.database import SessionLocal
from backend.app.services.detection_pipeline import run_detection

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0
_thread: threading.Thread | None = None
_stop = threading.Event()


def _now():
    return datetime.now(timezone.utc)


def reset_stuck_jobs() -> int:
    """进程重启时，把停在 running 的任务退回队列。

    不这么做的话，跑到一半的重启会让任务永远停在「进行中」，
    界面上是一个永远不动的进度条。
    """
    db = SessionLocal()
    try:
        n = (
            db.query(BatchJobDB)
            .filter(BatchJobDB.status == "running")
            .update({"status": "queued", "message": "服务重启，已重新排队"},
                    synchronize_session=False)
        )
        db.query(BatchJobItemDB).filter(BatchJobItemDB.status == "running").update(
            {"status": "queued"}, synchronize_session=False
        )
        db.commit()
        if n:
            logger.info("批量任务：%s 个中断的任务已重新排队", n)
        return n
    finally:
        db.close()


def _claim_next() -> int | None:
    """原子地领一个 queued 任务。返回 job id，没有则 None。"""
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "UPDATE batch_jobs SET status='running', updated_at=:now "
                "WHERE id = (SELECT id FROM batch_jobs WHERE status='queued' "
                "ORDER BY id LIMIT 1) RETURNING id"
            ),
            {"now": _now()},
        ).first()
        db.commit()
        return row[0] if row else None
    except Exception:
        # RETURNING 在很老的 SQLite 上没有；退回「先查再改」但仍用条件 UPDATE 兜底
        db.rollback()
        try:
            row = db.execute(
                text("SELECT id FROM batch_jobs WHERE status='queued' ORDER BY id LIMIT 1")
            ).first()
            if not row:
                return None
            res = db.execute(
                text("UPDATE batch_jobs SET status='running', updated_at=:now "
                     "WHERE id=:id AND status='queued'"),
                {"now": _now(), "id": row[0]},
            )
            db.commit()
            return row[0] if res.rowcount == 1 else None
        except Exception:
            db.rollback()
            raise
    finally:
        db.close()


def _cancelled(db, job_id: int) -> bool:
    db.expire_all()
    job = db.query(BatchJobDB).filter(BatchJobDB.id == job_id).first()
    return job is None or job.status == "cancelled"


def _run_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(BatchJobDB).filter(BatchJobDB.id == job_id).first()
        if job is None:
            return
        items = (
            db.query(BatchJobItemDB)
            .filter(BatchJobItemDB.job_id == job_id)
            .order_by(BatchJobItemDB.idx)
            .all()
        )

        for item in items:
            if item.status == "done":
                continue
            if _cancelled(db, job_id):
                logger.info("批量任务 %s 已取消", job_id)
                return

            item.status = "running"
            job.message = f"正在处理第 {item.idx + 1} / {len(items)} 组"
            db.commit()

            t1 = os.path.join(job.storage_dir, f"{item.idx}_t1.img")
            t2 = os.path.join(job.storage_dir, f"{item.idx}_t2.img")
            try:
                with open(t1, "rb") as f:
                    b1 = f.read()
                with open(t2, "rb") as f:
                    b2 = f.read()
                result = run_detection(
                    img1_bytes=b1,
                    img2_bytes=b2,
                    model=job.model,
                    threshold=job.threshold,
                    base_url=job.base_url,
                    db=db,
                    user_id=job.user_id,
                )
                item.status = "done"
                item.detection_id = result.get("detection_id")
                item.result_json = json.dumps(result, ensure_ascii=False)
                job.done += 1
            except Exception as e:  # noqa: BLE001
                # 一组失败不该拖垮整批：记下来接着跑下一组
                logger.warning("批量任务 %s 第 %s 组失败: %s", job_id, item.idx, e)
                item.status = "failed"
                item.error = str(getattr(e, "detail", e))[:250]
                job.failed += 1
            db.commit()

        db.refresh(job)
        if job.status != "cancelled":
            job.status = "done"
            job.message = "已完成"
            db.commit()
    except Exception as e:  # noqa: BLE001
        logger.exception("批量任务 %s 异常终止", job_id)
        db.rollback()
        job = db.query(BatchJobDB).filter(BatchJobDB.id == job_id).first()
        if job:
            job.status = "failed"
            job.message = str(e)[:250]
            db.commit()
    finally:
        db.close()


def _cleanup_files(job_id: int, storage_dir: str) -> None:
    try:
        shutil.rmtree(storage_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001
        logger.warning("清理批量任务 %s 的临时文件失败", job_id)


def _loop() -> None:
    logger.info("批量任务执行器已启动")
    while not _stop.is_set():
        try:
            job_id = _claim_next()
        except Exception:  # noqa: BLE001
            logger.exception("领取批量任务失败")
            job_id = None
        if job_id is None:
            _stop.wait(POLL_INTERVAL)
            continue
        try:
            _run_job(job_id)
        finally:
            db = SessionLocal()
            try:
                job = db.query(BatchJobDB).filter(BatchJobDB.id == job_id).first()
                # 已跑完或已取消就删掉上传的原始影像；失败的任务留着，方便排查
                if job and job.status in ("done", "cancelled") and job.storage_dir:
                    _cleanup_files(job_id, job.storage_dir)
            finally:
                db.close()


def start_worker() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="batch-runner", daemon=True)
    _thread.start()


def stop_worker() -> None:
    _stop.set()
