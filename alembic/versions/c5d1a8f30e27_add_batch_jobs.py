"""add batch_jobs / batch_job_items

Revision ID: c5d1a8f30e27
Revises: a3b9e5c02f14
Create Date: 2026-10-31

批量检测从「前端循环」搬到服务端任务表。关掉标签页后剩下的影像
仍然会被处理完，进度也不再随页面一起消失。

status 上建索引：worker 每 2 秒按 status='queued' 领任务，这是它的热路径。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5d1a8f30e27'
down_revision: Union[str, Sequence[str], None] = 'a3b9e5c02f14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'batch_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('model', sa.String(length=32), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('done', sa.Integer(), nullable=False),
        sa.Column('failed', sa.Integer(), nullable=False),
        sa.Column('base_url', sa.String(length=255), nullable=True),
        sa.Column('message', sa.String(length=255), nullable=True),
        sa.Column('storage_dir', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_batch_jobs_id'), 'batch_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_batch_jobs_status'), 'batch_jobs', ['status'], unique=False)
    op.create_index(op.f('ix_batch_jobs_user_id'), 'batch_jobs', ['user_id'], unique=False)

    op.create_table(
        'batch_job_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('idx', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('detection_id', sa.Integer(), nullable=True),
        sa.Column('error', sa.String(length=255), nullable=True),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['batch_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_batch_job_items_id'), 'batch_job_items', ['id'], unique=False)
    op.create_index(op.f('ix_batch_job_items_job_id'), 'batch_job_items', ['job_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_batch_job_items_job_id'), table_name='batch_job_items')
    op.drop_index(op.f('ix_batch_job_items_id'), table_name='batch_job_items')
    op.drop_table('batch_job_items')
    op.drop_index(op.f('ix_batch_jobs_user_id'), table_name='batch_jobs')
    op.drop_index(op.f('ix_batch_jobs_status'), table_name='batch_jobs')
    op.drop_index(op.f('ix_batch_jobs_id'), table_name='batch_jobs')
    op.drop_table('batch_jobs')
