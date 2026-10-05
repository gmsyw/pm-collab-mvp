"""任务卡编号改为「项目内唯一」：复合唯一 (project_id, code)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-05 14:00:00.000000

修复缺陷 DEF-01：原 TaskCard.code 为全局 unique，导致同编号在跨项目时互相挤占、
二次建同编号直接 409，违背需求书 §4.1「项目内唯一」。本迁移将 task_cards 的全局
唯一索引重建为复合唯一 (project_id, code)，存量数据保持不变（数据行复制）。
SQLite 不支持原地改唯一约束，采用「改名旧表 → 删旧命名索引 → 按新模型建表 → 复制
数据 → 删旧表」。注意：改名后旧表的命名索引（ix_task_cards_status 等）仍占用同名，
须先 DROP 再建新表，否则 CREATE INDEX 同名冲突。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text, UniqueConstraint
from sqlalchemy.dialects import postgresql

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None

# task_cards 上由模型 index=True 产生的命名索引，改名旧表后仍需先删除以免冲突
NAMED_INDEXES = (
    "ix_task_cards_status",
    "ix_task_cards_milestone_id",
    "ix_task_cards_work_package_id",
)


def _copy(bind) -> None:
    from server.app.models import TaskCard
    cols = [c.name for c in TaskCard.__table__.columns]
    col_sql = ", ".join(cols)
    bind.execute(
        sa.text(f"INSERT INTO task_cards ({col_sql}) SELECT {col_sql} FROM _task_cards_old")
    )


def upgrade() -> None:
    from server.app.models import TaskCard
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE task_cards RENAME TO _task_cards_old"))
    for idx in NAMED_INDEXES:
        bind.execute(sa.text(f"DROP INDEX IF EXISTS {idx}"))
    TaskCard.__table__.create(bind=bind)
    _copy(bind)
    bind.execute(sa.text("DROP TABLE _task_cards_old"))


def downgrade() -> None:
    from sqlalchemy import MetaData
    from server.app.models import TaskCard
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE task_cards RENAME TO _task_cards_old"))
    for idx in NAMED_INDEXES:
        bind.execute(sa.text(f"DROP INDEX IF EXISTS {idx}"))
    # 还原为 code 全局唯一
    meta = MetaData()
    clone = TaskCard.__table__.tometadata(meta, name="task_cards")
    clone.constraints = {
        c for c in clone.constraints
        if not (isinstance(c, UniqueConstraint)
                and set(c.columns.keys()) == {"project_id", "code"})
    }
    clone.append_constraint(UniqueConstraint("code", name="uq_task_cards_code"))
    clone.create(bind=bind)
    cols = [c.name for c in clone.columns]
    col_sql = ", ".join(cols)
    bind.execute(
        sa.text(f"INSERT INTO task_cards ({col_sql}) SELECT {col_sql} FROM _task_cards_old")
    )
    bind.execute(sa.text("DROP TABLE _task_cards_old"))
