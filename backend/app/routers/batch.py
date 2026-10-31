"""批量检测：建任务、查进度、取消。

与旧实现的关键差别：任务是**服务端的一条记录**，前端只负责上传和轮询。
以前是前端跑循环，关掉标签页剩下的影像就永远没人处理了。
"""

import json
import logging
import os
import shutil
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.core.timefmt import to_local
from backend.app.models.batch import BatchJobDB, BatchJobItemDB
from backend.app.models.user import UserDB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["批量检测"])

UPLOAD_ROOT = os.path.join("uploads", "batch")
MAX_ITEMS = 50
MAX_FILE_BYTES = 20 * 1024 * 1024


def _job_dict(job: BatchJobDB, items: list | None = None) -> dict:
    data = {
        "id": job.id,
        "status": job.status,
        "model": job.model,
        "threshold": job.threshold,
        "total": job.total,
        "done": job.done,
        "failed": job.failed,
        "message": job.message or "",
        "created_at": to_local(job.created_at),
        "updated_at": to_local(job.updated_at),
    }
    if items is not None:
        data["items"] = [
            {
                "idx": it.idx,
                "name": it.name,
                "status": it.status,
                "detection_id": it.detection_id,
                "error": it.error or "",
                "result": json.loads(it.result_json) if it.result_json else None,
            }
            for it in items
        ]
    return data


@router.post("/batch")
@limiter.limit("10/minute", key_func=get_user_key)
async def create_batch(
    request: Request,
    img1: list[UploadFile] = File(...),
    img2: list[UploadFile] = File(...),
    model: str = Form(...),
    threshold: float = Form(...),
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if len(img1) != len(img2):
        raise HTTPException(status_code=400, detail="前后时相影像数量不一致，无法配对")
    if not img1:
        raise HTTPException(status_code=400, detail="没有收到任何影像")
    if len(img1) > MAX_ITEMS:
        raise HTTPException(status_code=400, detail=f"单批最多 {MAX_ITEMS} 组，请分批提交")

    job = BatchJobDB(
        user_id=current_user.id,
        status="queued",
        model=model,
        threshold=float(threshold),
        total=len(img1),
        base_url=str(request.base_url).rstrip("/"),
        message="排队中",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    storage_dir = os.path.join(UPLOAD_ROOT, f"{job.id}-{uuid.uuid4().hex[:8]}")
    os.makedirs(storage_dir, exist_ok=True)
    job.storage_dir = storage_dir
    db.commit()

    try:
        for idx, (f1, f2) in enumerate(zip(img1, img2)):
            for slot, upload in ((f"{idx}_t1.img", f1), (f"{idx}_t2.img", f2)):
                target = os.path.join(storage_dir, slot)
                size = 0
                with open(target, "wb") as out:
                    # 流式落盘：批量最多 50 组，全读进内存会直接把进程撑爆
                    while chunk := await upload.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_FILE_BYTES:
                            raise HTTPException(
                                status_code=413,
                                detail=f"{upload.filename or '影像'} 超过 "
                                       f"{MAX_FILE_BYTES // 1024 // 1024} MB",
                            )
                        out.write(chunk)
            db.add(
                BatchJobItemDB(
                    job_id=job.id,
                    idx=idx,
                    name=(f1.filename or f"第 {idx + 1} 组")[:250],
                    status="queued",
                )
            )
        db.commit()
    except HTTPException:
        shutil.rmtree(storage_dir, ignore_errors=True)
        job.status = "failed"
        job.message = "上传失败"
        db.commit()
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("批量任务上传失败")
        shutil.rmtree(storage_dir, ignore_errors=True)
        job.status = "failed"
        job.message = str(e)[:250]
        db.commit()
        raise HTTPException(status_code=500, detail="影像上传失败")

    logger.info("批量任务已创建: id=%s 共 %s 组 user=%s", job.id, job.total, current_user.username)
    return {"code": 200, "data": _job_dict(job)}


@router.get("/batch")
@limiter.limit("60/minute", key_func=get_user_key)
def list_batches(
    request: Request,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jobs = (
        db.query(BatchJobDB)
        .filter(BatchJobDB.user_id == current_user.id)
        .order_by(BatchJobDB.id.desc())
        .limit(20)
        .all()
    )
    return {"code": 200, "data": [_job_dict(j) for j in jobs]}


@router.get("/batch/{job_id}")
@limiter.limit("120/minute", key_func=get_user_key)
def get_batch(
    request: Request,
    job_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(BatchJobDB)
        .filter(BatchJobDB.id == job_id, BatchJobDB.user_id == current_user.id)
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    items = (
        db.query(BatchJobItemDB)
        .filter(BatchJobItemDB.job_id == job_id)
        .order_by(BatchJobItemDB.idx)
        .all()
    )
    return {"code": 200, "data": _job_dict(job, items)}


@router.post("/batch/{job_id}/cancel")
@limiter.limit("30/minute", key_func=get_user_key)
def cancel_batch(
    request: Request,
    job_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(BatchJobDB)
        .filter(BatchJobDB.id == job_id, BatchJobDB.user_id == current_user.id)
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status in ("done", "failed"):
        raise HTTPException(status_code=400, detail="任务已结束，无法取消")
    # 只置标志位；worker 处理完当前这一组就会停下 —— 硬杀线程会留下
    # 半截的检测记录和结果文件
    job.status = "cancelled"
    job.message = "已取消"
    db.commit()
    logger.info("批量任务已取消: id=%s", job_id)
    return {"code": 200, "data": _job_dict(job)}
