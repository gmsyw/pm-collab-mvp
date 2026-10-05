"""add projects entity and project_id scoping

Revision ID: a1b2c3d4e5f6
Revises: 4f1a8a420872
Create Date: 2026-10-04 12:00:00.000000

项目成为 WBS 根实体（需求书 §4.1：项目→里程碑→工作包→任务；设计大纲决策点④
单项目优先、预留多项目）。业务实体均加 project_id，存量数据回填默认项目。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text  # JSONB astext_type 依赖
from sqlalchemy.dialects import postgresql

revision = 'a1b2c3d4e5f6'
down_revision = '4f1a8a420872'
branch_labels = None
depends_on = None

DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        'projects',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('owner', sa.String(length=128), nullable=False),
        sa.Column('extra', postgresql.JSONB(astext_type=Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )

    pid = sa.text(f"'{DEFAULT_PROJECT_ID}'")
    for tbl in (
        'task_cards', 'handoff_orders', 'doc_entries', 'version_ledger',
        'checkpoint_signals', 'metric_records', 'process_instances', 'gate_records',
    ):
        op.add_column(tbl, sa.Column('project_id', sa.String(length=36), nullable=False, server_default=pid))


def downgrade() -> None:
    for tbl in (
        'gate_records', 'process_instances', 'metric_records', 'checkpoint_signals',
        'version_ledger', 'doc_entries', 'handoff_orders', 'task_cards',
    ):
        op.drop_column(tbl, 'project_id')
    op.drop_table('projects')
