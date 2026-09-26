from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.app.models.database import Base


class AnnotationDB(Base):
    __tablename__ = "annotations"
    id = Column(Integer, primary_key=True, index=True)
    detection_id = Column(Integer, ForeignKey("detection_results.id"), unique=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    annotation_data = Column(String)  # JSON: base64 encoded mask image
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
