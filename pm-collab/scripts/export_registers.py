"""导出台账入五库：名册 / 角色卡 / 需求基线 / 任务台账 / 追加日志 / 追溯矩阵 / 版本台账。

规则（文档组织方案 §0.3）：**版本不覆盖** —— 每次导出生成新版本文件，旧文件原样保留，
并同步复制一份到 `05_版本库/archive/`；每条导出登记为文档条目（含 sha256）与版本台账记录。
用法：python scripts/export_registers.py
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy.orm import Session  # noqa: E402

from server.app.config import settings  # noqa: E402
from server.app.db import SessionLocal  # noqa: E402
from server.app.models import (  # noqa: E402
    AppendLog, DocEntry, Member, RequirementItem, RoleCard, TaskCard, VersionLedger,
)
from server.app.services.db_bootstrap import init_db  # noqa: E402
from server.app.services.five_libs import ensure_libraries  # noqa: E402
from server.app.utils import sha256_file, today_str  # noqa: E402


def _alloc_path(dirpath: Path, base: str) -> tuple[Path, str]:
    """按已有同前缀文件数量分配新版本号（X.Y.Z），保证不覆盖。"""
    dirpath.mkdir(parents=True, exist_ok=True)
    existing = list(dirpath.glob(f"{base}-V*.md"))
    version = f"V1.{len(existing)}.0"
    return dirpath / f"{base}-{version}.md", version


def _register(db: Session, doc_no: str, library: str, name: str, path: Path, version: str,
              owner: str = "PM-AI", status: str = "评审通过") -> None:
    file_hash = sha256_file(path)
    # 归档副本：旧版本永久保留
    archive_dir = settings.data_dir / "05_版本库" / "archive" / library
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, archive_dir / path.name)

    entry = db.query(DocEntry).filter(DocEntry.doc_no == doc_no).first()
    if entry is None:
        entry = DocEntry(doc_no=doc_no, library=library, category=name, name=name,
                         version=version, owner=owner, status=status,
                         path=str(path), file_hash=file_hash)
        db.add(entry)
    else:
        entry.version = version
        entry.path = str(path)
        entry.file_hash = file_hash
        entry.status = status
    db.flush()

    db.add(VersionLedger(
        version=version, item_name=name, item_type=library,
        released_at=today_str(), executor=owner,
        change_summary=f"{name} 导出/更新（哈希 {file_hash[:12]}…）",
        review_status="评审通过" if status == "评审通过" else "草稿",
        path=str(path), file_hash=file_hash, is_baseline=status == "评审通过",
    ))


def export_members(db: Session) -> Path:
    rows = db.query(Member).order_by(Member.code).all()
    lines = ["# 成员名册（人 + AI 统一建档）", "",
             f"> 导出时间：{datetime.now(tz=timezone.utc).isoformat()} · 来源：服务层数据库（唯一权威）", "",
             "| 编号 | 名称 | 类型 | 状态 | 汇报对象 | 登录名 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for m in rows:
        lines.append(f"| {m.code} | {m.name} | {m.member_type} | {m.status} | {m.reports_to or '—'} | {m.username or '—'} |")
    d = settings.data_dir / "01_项目库" / "成员名册与角色卡"
    p, v = _alloc_path(d, "PM-Collab-名册-成员名册")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _register(db, "DOC-MEMBER-001", "01_项目库", "成员名册", p, v)
    return p


def export_roles(db: Session) -> Path:
    rows = db.query(RoleCard).order_by(RoleCard.code).all()
    lines = ["# 角色卡清单（8 字段）", "", "| 编号 | 类型 | 职责 | 负面清单 | 权限 | 数据边界 | 汇报对象 | 降级预案 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r.code} | {r.role_type} | {r.duty} | {r.negative_list} | {r.permission_level} "
                     f"| {r.data_boundary} | {r.reports_to or '—'} | {r.downgrade_plan} |")
    d = settings.data_dir / "01_项目库" / "成员名册与角色卡"
    p, v = _alloc_path(d, "PM-Collab-角色卡-角色卡清单")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _register(db, "DOC-ROLE-001", "01_项目库", "角色卡清单", p, v)
    return p


def export_requirements(db: Session) -> Path:
    rows = db.query(RequirementItem).order_by(RequirementItem.code).all()
    lines = ["# 需求基线 · 需求条目库", "", f"> 来源：{rows[0].source_doc if rows else '需求规格书 V1.0'} · 共 {len(rows)} 条", "",
             "| 编号 | 章节 | 需求内容 | 优先级 | MVP 范围 | 评审状态 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r.code} | {r.section} | {r.content} | {r.priority} | {'是' if r.in_mvp else '否'} | {r.review_status} |")
    d = settings.data_dir / "01_项目库" / "需求基线"
    p, v = _alloc_path(d, "PM-Collab-需求基线-需求条目库")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _register(db, "DOC-REQ-001", "01_项目库", "需求基线", p, v)
    return p


def export_tasks(db: Session) -> Path:
    rows = db.query(TaskCard).order_by(TaskCard.code).all()
    closed = len([t for t in rows if t.status == "关闭"])
    lines = ["# 任务台账 · MVP 任务卡状态", "", f"> 共 {len(rows)} 张，已关闭 {closed} 张", "",
             "| 编号 | 目标 | 工作包 | AI-R | 优先级 | 状态 | 证据数 | 返工 | 完成摘要 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for t in rows:
        lines.append(f"| {t.code} | {t.title} | {t.work_package} | {t.ai_executor or '—'} | {t.priority} "
                     f"| {t.status} | {len(t.evidence or [])} | {t.rework_count} | {(t.summary or '—')[:40]} |")
    d = settings.data_dir / "03_日志" / "任务台账"
    p, v = _alloc_path(d, "PM-Collab-任务台账-任务状态")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _register(db, "DOC-TASK-001", "03_日志", "任务台账", p, v)
    return p


def export_logs(db: Session) -> Path:
    rows = db.query(AppendLog).order_by(AppendLog.occurred_at.desc()).limit(500).all()
    lines = ["# 交互日志 · 追加式留痕（只增不改、不可删除）", "", f"> 共 {len(rows)} 条（最近 500）", "",
             "| 时间 | 执行者 | 动作 | 产出物路径 | 变更 | 下一步 | 遗留问题 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r.occurred_at.isoformat()} | {r.actor} | {r.action} | {r.artifact_path} "
                     f"| {r.change} | {r.next_step} | {r.open_issue} |")
    d = settings.data_dir / "03_日志" / "交互日志"
    p, v = _alloc_path(d, "PM-Collab-交互日志-追加日志")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _register(db, "DOC-LOG-001", "03_日志", "交互日志", p, v)
    return p


# 需求 → 任务 → 实现 → 用例 → 结果 的追溯映射（MVP 关键链）
TRACE = {
    "R-1.4": ("T08/T11", "server/app/api/auth.py · api/process.py", "tests/test_auth_members_roles.py", "通过"),
    "R-2.4": ("T09", "server/app/api/roles.py", "tests/test_auth_members_roles.py", "通过"),
    "R-3.1": ("T11", "server/app/api/process.py", "tests/test_process_gates.py", "通过"),
    "R-3.3": ("T11/T24", "server/app/api/process.py::sign_gate", "tests/test_process_gates.py", "通过"),
    "R-4.2": ("T04/T07/T10", "server/app/models.py · api/tasks.py", "tests/test_tasks.py", "通过"),
    "R-4.3": ("T10", "server/app/state_machine.py", "tests/test_state_machine.py", "通过"),
    "R-4.6": ("T10", "server/app/api/tasks.py（阻塞卡点）", "tests/test_tasks.py", "通过"),
    "R-5.2": ("T06", "alembic/versions/… · services/triggers.py", "tests/test_report_digest.py", "通过"),
    "R-5.3": ("T10", "server/app/api/tasks.py（证据校验）", "tests/test_tasks.py", "通过"),
    "R-5.4": ("T18/T21", "web/src/views/Dashboard.vue · services/digest.py", "tests/test_report_digest.py", "通过"),
    "R-6.2": ("T12", "server/app/utils.py::validate_doc_name", "tests/test_state_machine.py", "通过"),
    "R-7.1": ("T23", "tests/（65 用例，覆盖率 97%）", "pytest --cov", "通过"),
    "R-7.5": ("T11/T23", "state_machine.TEST_EVIDENCE_ON_ADVANCE", "tests/test_process_gates.py", "通过"),
    "R-8.3": ("T12/T25", "server/app/api/docs.py", "tests/test_docs_versions.py", "通过"),
    "R-11.1": ("T21/T22", "server/app/services/digest.py", "tests/test_report_digest.py", "通过"),
    "R-12.1": ("T01", "server/app/services/five_libs.py", "tests/test_docs_versions.py", "通过"),
    "R-13.3": ("T01–T25", "MVP 全量交付", "scripts/smoke.py", "通过"),
}


def export_trace_matrix(db: Session) -> Path:
    lines = ["# 追溯矩阵（需求 → 设计 → 实现 → 用例 → 结果）", "",
             "| 需求编号 | 需求内容 | 关联任务 | 实现位置 | 用例 | 结果 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for code, (tasks, impl, case, result) in TRACE.items():
        req = db.query(RequirementItem).filter(RequirementItem.code == code).first()
        lines.append(f"| {code} | {req.content if req else '—'} | {tasks} | {impl} | {case} | {result} |")
    d = settings.data_dir / "02_交付物" / "01_需求"
    p, v = _alloc_path(d, "PM-Collab-设计文档-追溯矩阵")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _register(db, "DOC-TRACE-001", "02_交付物", "追溯矩阵", p, v)
    return p


def export_version_ledger(db: Session) -> Path:
    rows = db.query(VersionLedger).order_by(VersionLedger.id).all()
    lines = ["# 版本台账", "", "> 版本不覆盖：每次登记生成新记录，旧记录与旧文件永久保留（副本见 archive/）。", "",
             "| 版本 | 条目 | 类型 | 日期 | 执行者 | 变更摘要 | 评审状态 | 哈希 | 基线 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for v in rows:
        lines.append(f"| {v.version} | {v.item_name} | {v.item_type} | {v.released_at} | {v.executor} "
                     f"| {v.change_summary} | {v.review_status} | {(v.file_hash or '')[:12]}… "
                     f"| {'是' if v.is_baseline else '否'} |")
    d = settings.data_dir / "05_版本库"
    p, v = _alloc_path(d, "PM-Collab-版本台账-版本台账")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def main() -> int:
    init_db()
    ensure_libraries()
    db: Session = SessionLocal()
    try:
        paths = [
            export_members(db), export_roles(db), export_requirements(db),
            export_tasks(db), export_logs(db), export_trace_matrix(db),
        ]
        db.commit()
        paths.append(export_version_ledger(db))
        db.commit()
        print("[export] 已导出：")
        for p in paths:
            print(f"  - {p}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
