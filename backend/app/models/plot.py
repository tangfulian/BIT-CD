from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from backend.app.models.database import Base


class PlotDB(Base):
    __tablename__ = "plots"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    province = Column(String(50), default="")
    city = Column(String(50), default="")
    lat_lng = Column(String(200), default="")
    area = Column(Float, default=0)
    land_type = Column(String(50), default="")
    crop_type = Column(String(50), default="")
    data_source = Column(String(50), default="")
    change_type = Column(String(100), default="黑土层变薄退化")
    t1_time = Column(String(50), default="")
    t2_time = Column(String(50), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
