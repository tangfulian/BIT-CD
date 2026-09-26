from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, text

from backend.app.models.database import Base


class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String, default="user")
    disabled = Column(Integer, default=0, server_default=text("0"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
