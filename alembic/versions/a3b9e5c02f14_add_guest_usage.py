"""add guest_usage

Revision ID: a3b9e5c02f14
Revises: 7d2f4c81ba60
Create Date: 2026-10-31

游客免费额度的服务端计数。

主键是 (ip, day) 组合：按天重置，因为共用出口 IP 的场景（教室、办公室）
下永久计数会让后来的人一次都试不了。旧行由应用侧顺手清理，不做定时任务。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3b9e5c02f14'
down_revision: Union[str, Sequence[str], None] = '7d2f4c81ba60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'guest_usage',
        sa.Column('ip', sa.String(length=64), nullable=False),
        sa.Column('day', sa.String(length=10), nullable=False),
        sa.Column('used', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.PrimaryKeyConstraint('ip', 'day'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('guest_usage')
