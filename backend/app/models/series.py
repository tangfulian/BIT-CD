from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from backend.app.models.database import Base


class ImageSeriesDB(Base):
    """多时相影像序列。

    一个序列代表同一地块的 N 期观测（N≥2）。序列本身只存元信息，
    具体的期次是挂在它下面的检测记录 —— 每两条相邻影像构成一个区间，
    即一条 DetectionResultDB，用 phase_index 标记它是第几个区间（0 基）。

    这样设计的好处是完全复用既有的检测链路：每一对影像仍然走 /detect，
    结果图、概率图、重调阈值等能力一个都不用重写。
    """

    __tablename__ = "image_series"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    location = Column(String(50), default="")
    lat_lng = Column(String(200), default="")
    # 地块面积（亩）。留空时速率只能以 %/年 表达；填了才能换算成亩/年。
    area_mu = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
