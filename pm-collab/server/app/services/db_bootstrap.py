"""数据库初始化：建表 + 库层追加日志约束 + 默认管理成员。"""
from __future__ import annotations

from sqlalchemy import text

from ..db import Base, engine
from ..models import DEFAULT_PROJECT_ID, AppendLog  # noqa: F401  # 确保模型注册
from .triggers import statements_for


def init_db() -> list[str]:
    Base.metadata.create_all(engine)
    applied: list[str] = []
    dialect = engine.dialect.name
    with engine.begin() as conn:
        for sql in statements_for(dialect):
            conn.execute(text(sql.strip()))
            applied.append(sql.strip().split("\n")[0][:60])
        # 兜底：为既有库补齐 role_cards.project_id 列（MVP 开发态平滑升级）
        if dialect == "sqlite":
            try:
                cols = [r[1] for r in conn.execute(text("PRAGMA table_info(role_cards)")).fetchall()]
                if "project_id" not in cols:
                    conn.execute(text(
                        "ALTER TABLE role_cards ADD COLUMN project_id VARCHAR(36) NOT NULL DEFAULT 'default'"
                    ))
                    applied.append("ALTER role_cards ADD project_id")
            except Exception as exc:  # 表尚未存在等情况忽略
                applied.append(f"skip role_cards alter: {exc}")
            # DEF-07：doc_entries.doc_no 由全局唯一改为 (project_id, doc_no) 复合唯一。
            # SQLite 无法 ALTER 列约束，旧表若含单列 UNIQUE(doc_no) 则整表重建（数据迁移）。
            try:
                existing = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='doc_entries'"
                )).fetchone()
                needs_rebuild = False
                if existing:
                    for r in conn.execute(text("PRAGMA index_list(doc_entries)")).fetchall():
                        if r[2] == 1:  # unique
                            idx_name = r[1]  # index_list 返回 (seq, name, unique, origin, partial)
                            cols = [c[2] for c in conn.execute(
                                text(f"PRAGMA index_info({idx_name})")).fetchall()]
                            if cols == ["doc_no"]:
                                needs_rebuild = True
                                break
                if needs_rebuild:
                    conn.execute(text("ALTER TABLE doc_entries RENAME TO doc_entries_old"))
                    conn.execute(text(
                        "CREATE TABLE doc_entries ("
                        " id VARCHAR(36) NOT NULL, project_id VARCHAR(36) NOT NULL,"
                        " doc_no VARCHAR(64) NOT NULL, library VARCHAR(16), category VARCHAR(64),"
                        " name VARCHAR(256) NOT NULL, version VARCHAR(16), owner VARCHAR(128),"
                        " status VARCHAR(16), path TEXT, file_hash VARCHAR(128), extra TEXT,"
                        " created_at DATETIME, updated_at DATETIME,"
                        " PRIMARY KEY (id),"
                        " CONSTRAINT uq_doc_entries_project_docno UNIQUE (project_id, doc_no))"
                    ))
                    conn.execute(text(
                        "INSERT INTO doc_entries (id, project_id, doc_no, library, category, name,"
                        " version, owner, status, path, file_hash, extra, created_at, updated_at)"
                        " SELECT id, project_id, doc_no, library, category, name, version, owner,"
                        " status, path, file_hash, extra, created_at, updated_at FROM doc_entries_old"
                    ))
                    conn.execute(text("DROP TABLE doc_entries_old"))
                    applied.append("rebuilt doc_entries -> 复合唯一(project_id,doc_no)")
            except Exception as exc:
                applied.append(f"skip doc_entries rebuild: {exc}")
            # 兜底：将历史字面量 "default" 归属规范化到 DEFAULT_PROJECT_ID，
            # 统一"默认项目"语义，便于新建项目克隆其名册/角色卡（幂等）。
            try:
                for tbl in ("members", "role_cards"):
                    conn.execute(text(
                        f"UPDATE {tbl} SET project_id = :pid WHERE project_id = 'default'"
                    ), {"pid": DEFAULT_PROJECT_ID})
            except Exception as exc:  # 列尚未存在等情况忽略
                applied.append(f"skip default normalize: {exc}")
            # DEF-08 修复（V0.4）：补齐任务卡/交接单新增列（开发态平滑升级，幂等）。
            # 必须在 with 事务内执行，确保 conn 可用；列已存在则跳过。
            try:
                for (tbl, col, ddl) in [
                    ("members", "token_valid_from", "token_valid_from DATETIME"),
                    ("task_cards", "parent_task_id", "parent_task_id VARCHAR(36)"),
                    ("task_cards", "module_tag", "module_tag VARCHAR(16)"),
                    ("handoff_orders", "event_type", "event_type VARCHAR(32) NOT NULL DEFAULT ''"),
                    ("handoff_orders", "round", "round INTEGER NOT NULL DEFAULT 0"),
                    ("handoff_orders", "evidence", "evidence TEXT"),
                ]:
                    cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({tbl})")).fetchall()]
                    if col not in cols:
                        conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {ddl}"))
                        applied.append(f"ALTER {tbl} ADD {col}")
            except Exception as exc:
                applied.append(f"skip v04 columns: {exc}")
    return applied
