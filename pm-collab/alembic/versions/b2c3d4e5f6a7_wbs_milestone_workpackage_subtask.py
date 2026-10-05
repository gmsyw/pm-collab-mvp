"""WBS 四层 + 子任务：里程碑/工作包/子任务三表 + 任务卡关联列 + 存量回填

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-05 10:00:00.000000

需求书 §4.1 分解层级：项目→里程碑→工作包→任务，任务之下再拆一层子任务。
将原本落在任务卡上的 milestone / work_package 自由文本升级为实体（milestones /
work_packages）并建立 task_cards.milestone_id / work_package_id 外键关联；
存量任务的自由文本被回填为对应实体，保证既有 30 张任务卡继续可见、可追溯。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000001"
JsonVar = postgresql.JSONB(astext_type=Text()).with_variant(sa.JSON(), 'sqlite')


def upgrade() -> None:
    op.create_table(
        'milestones',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False, server_default=sa.text(f"'{DEFAULT_PROJECT_ID}'")),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default=sa.text("'进行中'")),
        sa.Column('owner', sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column('start_date', sa.String(length=32), nullable=True),
        sa.Column('due_date', sa.String(length=32), nullable=True),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('extra', JsonVar, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_milestones_project_id', 'milestones', ['project_id'])

    op.create_table(
        'work_packages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False, server_default=sa.text(f"'{DEFAULT_PROJECT_ID}'")),
        sa.Column('milestone_id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default=sa.text("'进行中'")),
        sa.Column('owner', sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column('start_date', sa.String(length=32), nullable=True),
        sa.Column('due_date', sa.String(length=32), nullable=True),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('extra', JsonVar, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_work_packages_project_id', 'work_packages', ['project_id'])
    op.create_index('ix_work_packages_milestone_id', 'work_packages', ['milestone_id'])

    op.create_table(
        'sub_tasks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False, server_default=sa.text(f"'{DEFAULT_PROJECT_ID}'")),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default=sa.text("'待办'")),
        sa.Column('assignee', sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column('priority', sa.String(length=8), nullable=False, server_default=sa.text("'P2'")),
        sa.Column('due_date', sa.String(length=32), nullable=True),
        sa.Column('evidence', JsonVar, nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('extra', JsonVar, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sub_tasks_project_id', 'sub_tasks', ['project_id'])
    op.create_index('ix_sub_tasks_task_id', 'sub_tasks', ['task_id'])

    op.add_column('task_cards', sa.Column('milestone_id', sa.String(length=36), nullable=True))
    op.add_column('task_cards', sa.Column('work_package_id', sa.String(length=36), nullable=True))
    op.create_index('ix_task_cards_milestone_id', 'task_cards', ['milestone_id'])
    op.create_index('ix_task_cards_work_package_id', 'task_cards', ['work_package_id'])

    _backfill()


def _backfill() -> None:
    """将存量 task_cards 的 milestone / work_package 自由文本升级为实体关联。"""
    bind = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    # 1) 里程碑：按去重后的 milestone 文本各建一行
    ms_rows = bind.execute(sa.text("SELECT DISTINCT milestone FROM task_cards WHERE milestone IS NOT NULL AND milestone != ''")).fetchall()
    ms_map: dict[str, str] = {}
    for (name,) in ms_rows:
        mid = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO milestones (id, project_id, code, name, description, status, owner, "
                "start_date, due_date, order_index, extra, created_at, updated_at) "
                "VALUES (:id, :pid, :code, :name, '', '进行中', '', NULL, NULL, 0, NULL, :now, :now)"
            ),
            {"id": mid, "pid": DEFAULT_PROJECT_ID, "code": name, "name": name, "now": now},
        )
        ms_map[name] = mid

    # 2) 工作包：按 (milestone, work_package) 去重建一行，code 取首词（如 "WP0 项目准备" → "WP0"）
    wp_rows = bind.execute(
        sa.text(
            "SELECT DISTINCT milestone, work_package FROM task_cards "
            "WHERE work_package IS NOT NULL AND work_package != ''"
        )
    ).fetchall()
    wp_map: dict[tuple[str, str], str] = {}
    for mname, wpname in wp_rows:
        mid = ms_map.get(mname)
        if not mid:
            continue
        code = wpname.split(" ", 1)[0] if wpname else wpname
        wid = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO work_packages (id, project_id, milestone_id, code, name, description, "
                "status, owner, start_date, due_date, order_index, extra, created_at, updated_at) "
                "VALUES (:id, :pid, :mid, :code, :name, '', '进行中', '', NULL, NULL, 0, NULL, :now, :now)"
            ),
            {"id": wid, "pid": DEFAULT_PROJECT_ID, "mid": mid, "code": code, "name": wpname, "now": now},
        )
        wp_map[(mname, wpname)] = wid

    # 3) 回填 task_cards 关联列
    tasks = bind.execute(sa.text("SELECT id, milestone, work_package FROM task_cards")).fetchall()
    for tid, mname, wpname in tasks:
        mid = ms_map.get(mname)
        wid = wp_map.get((mname, wpname)) if wpname else None
        bind.execute(
            sa.text("UPDATE task_cards SET milestone_id = :mid, work_package_id = :wid WHERE id = :tid"),
            {"mid": mid, "wid": wid, "tid": tid},
        )


def downgrade() -> None:
    op.drop_index('ix_task_cards_work_package_id', table_name='task_cards')
    op.drop_index('ix_task_cards_milestone_id', table_name='task_cards')
    op.drop_column('task_cards', 'work_package_id')
    op.drop_column('task_cards', 'milestone_id')
    op.drop_index('ix_sub_tasks_task_id', table_name='sub_tasks')
    op.drop_index('ix_sub_tasks_project_id', table_name='sub_tasks')
    op.drop_table('sub_tasks')
    op.drop_index('ix_work_packages_milestone_id', table_name='work_packages')
    op.drop_index('ix_work_packages_project_id', table_name='work_packages')
    op.drop_table('work_packages')
    op.drop_index('ix_milestones_project_id', table_name='milestones')
    op.drop_table('milestones')
