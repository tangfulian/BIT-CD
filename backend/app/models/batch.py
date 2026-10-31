from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from backend.app.models.database import Base


class BatchJobDB(Base):
    """一批检测任务。

    此前批量检测是**前端的一个循环**：页面一关，剩下的影像就再也不会被处理，
    而界面上的进度条也随页面一起消失。搬到这里之后，任务是服务端的一条记录，
    关掉浏览器再打开还能接着看结果。
    """

    __tablename__ = "batch_jobs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="queued", index=True)
    # queued | running | done | failed | cancelled

    model = Column(String(32), nullable=False)
    threshold = Column(Float, nullable=False)
    total = Column(Integer, nullable=False, default=0)
    done = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)

    # 建任务时请求的站点地址。结果图 URL 要用它拼 —— 任务可能在很久之后才跑，
    # 那时候没法再去问「当前请求是谁」。
    base_url = Column(String(255), default="")
    message = Column(String(255), default="")
    storage_dir = Column(Text, default="")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class BatchJobItemDB(Base):
    __tablename__ = "batch_job_items"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("batch_jobs.id"), nullable=False, index=True)
    idx = Column(Integer, nullable=False)
    name = Column(String(255), default="")
    status = Column(String(16), nullable=False, default="queued")
    detection_id = Column(Integer, nullable=True)
    error = Column(String(255), default="")
    # 成功那一条的完整结果（掩膜/热力图/融合图 URL 与统计）。
    # 存在这里而不是让前端逐条再去查历史，一次轮询就能拿到全部。
    result_json = Column(Text, default="")
