"""add oauth_accounts

Revision ID: 4c9e2b7a1d33
Revises: b3f7a1c92e04
Create Date: 2026-10-31

第三方登录绑定表。

唯一约束必须建在 (provider, provider_uid) 这个组合上，不能只建在 provider 上：
同一个人反复登录要落到同一条记录，而一个本地用户允许同时绑 GitHub 和以后可能
加的微信 —— 两种方向都需要，只有组合唯一能同时满足。

provider_uid 用 String 而不是 Integer：GitHub 的 id 现在是整数，但 QQ 的 openid
是字符串。类型定成整数，接第二家时就得改表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c9e2b7a1d33'
down_revision: Union[str, Sequence[str], None] = 'b3f7a1c92e04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'oauth_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('provider_uid', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'provider', 'provider_uid', name='uq_oauth_provider_uid'
        ),
    )
    op.create_index(
        op.f('ix_oauth_accounts_id'), 'oauth_accounts', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_oauth_accounts_provider_uid'),
        'oauth_accounts',
        ['provider_uid'],
        unique=False,
    )
    op.create_index(
        op.f('ix_oauth_accounts_user_id'),
        'oauth_accounts',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_oauth_accounts_user_id'), table_name='oauth_accounts')
    op.drop_index(
        op.f('ix_oauth_accounts_provider_uid'), table_name='oauth_accounts'
    )
    op.drop_index(op.f('ix_oauth_accounts_id'), table_name='oauth_accounts')
    op.drop_table('oauth_accounts')
