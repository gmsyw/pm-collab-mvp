"""数据库初始化：建表 + 库层追加日志约束 + 默认管理成员。"""
from __future__ import annotations

from sqlalchemy import text

from ..db import Base, engine
from ..models import AppendLog  # noqa: F401  # 确保模型注册
from .triggers import statements_for


def init_db() -> list[str]:
    Base.metadata.create_all(engine)
    applied: list[str] = []
    dialect = engine.dialect.name
    with engine.begin() as conn:
        for sql in statements_for(dialect):
            conn.execute(text(sql.strip()))
            applied.append(sql.strip().split("\n")[0][:60])
    return applied
