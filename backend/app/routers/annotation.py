import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.annotation import AnnotationDB
from backend.app.models.detection import DetectionResultDB
from backend.app.models.user import UserDB
from backend.app.schemas.detection import AnnotationSaveRequest

router = APIRouter(prefix="/annotation", tags=["标注"])
logger = logging.getLogger(__name__)


@router.post("/{detection_id}")
@limiter.limit("20/minute", key_func=get_user_key)
def save_annotation(
    request: Request,
    detection_id: int,
    req: AnnotationSaveRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    detection = db.query(DetectionResultDB).filter(DetectionResultDB.id == detection_id).first()
    if not detection:
        raise HTTPException(status_code=404, detail="检测记录不存在")
    if current_user.role != "admin" and detection.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    from datetime import datetime, timezone

    existing = db.query(AnnotationDB).filter(AnnotationDB.detection_id == detection_id).first()
    if existing:
        existing.annotation_data = req.annotation_data
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            AnnotationDB(
                detection_id=detection_id,
                user_id=current_user.id,
                annotation_data=req.annotation_data,
            )
        )
    db.commit()
    return {"code": 200, "msg": "标注已保存"}


@router.get("/{detection_id}")
@limiter.limit("30/minute", key_func=get_user_key)
def get_annotation(
    request: Request,
    detection_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    detection = db.query(DetectionResultDB).filter(DetectionResultDB.id == detection_id).first()
    if not detection:
        raise HTTPException(status_code=404, detail="检测记录不存在")
    if current_user.role != "admin" and detection.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    annotation = db.query(AnnotationDB).filter(AnnotationDB.detection_id == detection_id).first()
    return {
        "code": 200,
        "data": {"annotation_data": annotation.annotation_data if annotation else None},
    }
