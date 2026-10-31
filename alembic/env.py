import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

from backend.app.core.config import DATABASE_URL
from backend.app.models.database import Base

# Import all models so metadata is fully populated
import backend.app.models.user  # noqa: E402, F401
import backend.app.models.detection  # noqa: E402, F401
import backend.app.models.annotation  # noqa: E402, F401
import backend.app.models.plot  # noqa: E402, F401
import backend.app.models.series  # noqa: E402, F401
import backend.app.models.oauth  # noqa: E402, F401
import backend.app.models.paper  # noqa: E402, F401
import backend.app.models.guest_usage  # noqa: E402, F401
import backend.app.models.batch  # noqa: E402, F401

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# 只有从 alembic 命令行跑时才套用 alembic.ini 的日志配置。
#
# alembic.ini 的 [logger_root] 是 level=WARNING 加一个指向 stderr 的 console
# handler，而 fileConfig 会**替换掉 root 上的全部 handler**。问题在于程序内
# 启动时（main.create_app → init_db → command.upgrade）root 上已经挂着
# core/logging_config 装好的 console + logs/app.log 文件 handler，被这么一换：
#
#     - 文件 handler 没了 → logs/app.log 永远是 0 字节
#     - root 级别从 DEBUG 变成 WARNING → 应用里所有 logger.info 被丢弃
#
# 也就是「应用日志一条都不落地」，而且不报任何错。调用方通过 attributes
# 显式关掉它（见 models/database.py 的 init_db）。
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
