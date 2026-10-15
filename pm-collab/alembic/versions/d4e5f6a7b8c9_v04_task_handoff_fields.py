"""V0.4：任务卡父子链/模块标签 + 交接单结构化事件字段

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-10 12:00:00.000000

对应《设计大纲 V0.4》§4/§11：任务卡增加 parent_task_id（父子任务链）、
module_tag（模块泳道聚合键 S1~S8）；交接单增加 event_type / round / evidence
三个结构化事件字段（M3 起新建交接单强制填写，迁移数据由服务层正则推断）。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None

JsonVar = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')


def upgrade() -> None:
    op.add_column('task_cards', sa.Column('parent_task_id', sa.String(length=36), nullable=True))
    op.create_index('ix_task_cards_parent_task_id', 'task_cards', ['parent_task_id'])
    op.add_column('task_cards', sa.Column('module_tag', sa.String(length=16), nullable=True))
    op.create_index('ix_task_cards_module_tag', 'task_cards', ['module_tag'])

    op.add_column('handoff_orders', sa.Column('event_type', sa.String(length=32), nullable=False,
                                              server_default=sa.text("''")))
    op.add_column('handoff_orders', sa.Column('round', sa.Integer(), nullable=False,
                                             server_default=sa.text('0')))
    op.add_column('handoff_orders', sa.Column('evidence', JsonVar, nullable=True))


def downgrade() -> None:
    op.drop_column('handoff_orders', 'evidence')
    op.drop_column('handoff_orders', 'round')
    op.drop_column('handoff_orders', 'event_type')
    op.drop_index('ix_task_cards_module_tag', table_name='task_cards')
    op.drop_column('task_cards', 'module_tag')
    op.drop_index('ix_task_cards_parent_task_id', table_name='task_cards')
    op.drop_column('task_cards', 'parent_task_id')
