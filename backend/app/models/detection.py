from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from backend.app.models.database import Base


class DetectionResultDB(Base):
    __tablename__ = "detection_results"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    model = Column(String)
    threshold = Column(Float)
    ratio = Column(Float)
    change_pixel = Column(Integer)
    total_pixel = Column(Integer)
    lat_lng = Column(String, default="")
    location = Column(String, default="")
    change_type = Column(String, default="")
    t1_time = Column(String, default="")
    t2_time = Column(String, default="")
    ai_change_type = Column(String, default="")
    ai_confidence = Column(Float, default=0.0)
    mask_url = Column(String)
    heat_url = Column(String)
    fusion_url = Column(String)
    score_url = Column(String, default="")
    image_pair_hash = Column(String(64), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
