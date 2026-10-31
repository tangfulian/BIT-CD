"""add paper_summaries

Revision ID: 7d2f4c81ba60
Revises: 4c9e2b7a1d33
Create Date: 2026-10-31

arXiv 论文中文摘要的缓存表。

为什么进库而不是只放内存：每生成一条都是一次真实的付费 LLM 调用，
服务重启或容器重建不该让我们把同一篇论文再翻一遍。arxiv_id 直接做主键 ——
一篇论文只会有一条摘要。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d2f4c81ba60'
down_revision: Union[str, Sequence[str], None] = '4c9e2b7a1d33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'paper_summaries',
        sa.Column('arxiv_id', sa.String(length=64), nullable=False),
        sa.Column('summary_zh', sa.Text(), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('arxiv_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('paper_summaries')
