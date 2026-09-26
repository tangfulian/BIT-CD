import os
import sys
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.app.core.config import DATABASE_URL, _is_sqlite

logger = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite(DATABASE_URL) else {},
)
SessionLocal = sessionmaker(autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    from alembic import command
    from alembic.config import Config as AlembicConfig

    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    alembic_ini = os.path.join(_project_root, "alembic.ini")
    alembic_cfg = AlembicConfig(alembic_ini)

    inspector = inspect(engine)
    has_alembic = "alembic_version" in inspector.get_table_names()

    if not has_alembic:
        has_users = "users" in inspector.get_table_names()
        if has_users:
            logger.info("检测到已有数据库，标记当前状态为最新迁移")
            command.stamp(alembic_cfg, "head")
        else:
            logger.info("新数据库，执行迁移创建所有表")
            command.upgrade(alembic_cfg, "head")
    else:
        command.upgrade(alembic_cfg, "head")

    if not _is_sqlite(DATABASE_URL):
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.commit()
