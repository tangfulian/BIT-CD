from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from backend.app.models.database import Base


class OAuthAccountDB(Base):
    """第三方登录绑定。

    (provider, provider_uid) 是提供方那边的身份，全局唯一 —— 同一个人重复登录
    必须落到同一条记录上，所以这里不能只按 provider 建索引。

    不去匹配 username：GitHub 的用户名可以被别人注册，若按用户名自动合并，
    攻击者注册一个同名的 GitHub 账号就能登进别人的本地账号。因此第三方登录
    一律新建独立账号，要合并只能在登录之后手动绑定。
    """

    __tablename__ = "oauth_accounts"
    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(32), nullable=False)
    provider_uid = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("provider", "provider_uid", name="uq_oauth_provider_uid"),
    )
