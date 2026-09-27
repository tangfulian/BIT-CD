"""add_image_series

Revision ID: b3f7a1c92e04
Revises: 1efe136d3d20
Create Date: 2026-09-27

新增多时相影像序列表，并把检测记录挂到序列上。

注意两点：

1. 这个迁移是手写的，不是 autogenerate 的产物。原因是模型与迁移链已经漂移 ——
   detection_results 的 t2_time / ai_change_type / ai_confidence 三列在模型里有、
   却不在任何迁移里（当前生产库是靠 stamp("head") 认下来的既有库）。既然基线
   与模型不一致，autogenerate 会生成一堆无关的增删，不如手写。

2. SQLite 不支持给既有表增加外键约束（ALTER TABLE 只能加列），所以这里按方言
   分支：SQLite 只加列，其他数据库连外键一起加。SQLite 默认也不强制外键，
   因此这个差别不影响实际行为；模型里声明的 ForeignKey 仍会被
   Base.metadata.create_all 使用（测试走这条路，全新库也走这条路）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f7a1c92e04'
down_revision: Union[str, Sequence[str], None] = '1efe136d3d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'image_series',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('location', sa.String(length=50), nullable=True),
        sa.Column('lat_lng', sa.String(length=200), nullable=True),
        sa.Column('area_mu', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_image_series_id'), 'image_series', ['id'], unique=False)

    is_sqlite = op.get_bind().dialect.name == 'sqlite'
    if is_sqlite:
        op.add_column(
            'detection_results',
            sa.Column('series_id', sa.Integer(), nullable=True),
        )
    else:
        op.add_column(
            'detection_results',
            sa.Column(
                'series_id',
                sa.Integer(),
                sa.ForeignKey('image_series.id'),
                nullable=True,
            ),
        )
    op.add_column(
        'detection_results', sa.Column('phase_index', sa.Integer(), nullable=True)
    )
    # series_id 会被按序列查询，必须建索引（image_pair_hash 当年漏建，
    # 导致去重查询走全表扫描，不要重复这个错误）
    op.create_index(
        op.f('ix_detection_results_series_id'),
        'detection_results',
        ['series_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_detection_results_series_id'), table_name='detection_results'
    )
    op.drop_column('detection_results', 'phase_index')
    op.drop_column('detection_results', 'series_id')
    op.drop_index(op.f('ix_image_series_id'), table_name='image_series')
    op.drop_table('image_series')
