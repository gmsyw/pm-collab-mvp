"""文档条目 / 版本台账 / 五库托管（E 文档与版本域；T12）。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..audit import raise_checkpoint, write_log
from ..config import settings
from ..models import DocEntry, Member, VersionLedger
from ..schemas import DocEntryIn, VersionIn
from ..utils import sha256_file, today_str, validate_doc_name
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api", tags=["文档与版本"])


# ---------------- 五库托管 ----------------
@router.get("/libs/tree")
def libs_tree(
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    """返回五库 + 交接区的目录托管状态。"""
    return {"data_dir": str(settings.data_dir), "libraries": _scan_libraries()}


def _scan_libraries() -> list[dict]:
    root = settings.data_dir
    if not root.exists():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        files = [f for f in d.rglob("*") if f.is_file()]
        out.append({"name": d.name, "path": str(d), "file_count": len(files)})
    return out


# ---------------- 文档条目 ----------------
@router.get("/docs")
def list_docs(
    library: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    q = db.query(DocEntry).filter(DocEntry.project_id == pid)
    if library:
        q = q.filter(DocEntry.library == library)
    if status_:
        q = q.filter(DocEntry.status == status_)
    rows = q.order_by(DocEntry.doc_no).all()
    return [
        {
            "id": r.id, "doc_no": r.doc_no, "library": r.library, "category": r.category,
            "name": r.name, "version": r.version, "owner": r.owner, "status": r.status,
            "path": r.path, "file_hash": r.file_hash, "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/docs", status_code=status.HTTP_201_CREATED)
def create_doc(
    payload: DocEntryIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    data = payload.model_dump()
    path = data.get("path") or ""
    ok, msg = validate_doc_name(Path(path).name or f"{'-'.join(['PM-Collab', '模板', data['name'], data['version']])}.md")
    if path and not ok:
        raise HTTPException(status_code=422, detail=f"文档命名不合规：{msg}")

    obj = DocEntry(**data, project_id=pid)
    obj.file_hash = sha256_file(path) if path and Path(path).exists() else ""
    db.add(obj)
    db.flush()
    write_log(db, actor=actor.name, action="登记文档条目",
              change=f"{obj.doc_no} {obj.name} {obj.version}", artifact_path=obj.path)
    db.commit()
    return {"id": obj.id, "doc_no": obj.doc_no, "file_hash": obj.file_hash}


@router.get("/docs/{doc_id}/verify")
def verify_doc(
    doc_id: str,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """哈希校验：不匹配即告警（设计大纲 T12 验收）。"""
    obj = db.get(DocEntry, doc_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="文档条目不存在")
    current_hash = sha256_file(obj.path)
    if not current_hash:
        return {"doc_no": obj.doc_no, "status": "文件缺失", "alert": True}
    matched = current_hash == obj.file_hash
    if not matched:
        write_log(db, actor=actor.name, action="文档哈希校验告警",
                  change=f"{obj.doc_no} 哈希不匹配（登记 {obj.file_hash[:12]}… vs 当前 {current_hash[:12]}…）",
                  artifact_path=obj.path, open_issue="疑似文件被改写，需核实版本")
        raise_checkpoint(
            db, trigger=actor.name, task_code=None, project_id=obj.project_id, category="越权失效",
            content=f"文档 {obj.doc_no}（{obj.path}）哈希不匹配，基线文件疑似被改写",
            human_action="核实变更来源，决定是否回滚或生成新版本（勿覆盖旧版本）",
            expect_by="当日",
        )
        db.commit()
    return {
        "doc_no": obj.doc_no, "status": "哈希一致" if matched else "哈希不匹配告警",
        "alert": not matched, "registered_hash": obj.file_hash, "current_hash": current_hash,
    }


@router.get("/requirements")
def list_requirements(
    in_mvp: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    """需求条目库（追溯矩阵左端：需求 → 设计 → 实现 → 用例 → 结果）。"""
    from ..models import RequirementItem

    q = db.query(RequirementItem)
    if in_mvp is not None:
        q = q.filter(RequirementItem.in_mvp == in_mvp)
    rows = q.order_by(RequirementItem.code).all()
    return [
        {
            "id": r.id, "code": r.code, "section": r.section, "content": r.content,
            "priority": r.priority, "in_mvp": r.in_mvp, "review_status": r.review_status,
            "source_doc": r.source_doc, "trace_links": r.trace_links,
        }
        for r in rows
    ]


# ---------------- 版本台账（只增不改） ----------------
@router.get("/versions")
def list_versions(
    item_name: str | None = Query(default=None),
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    q = db.query(VersionLedger).filter(VersionLedger.project_id == pid)
    if item_name:
        q = q.filter(VersionLedger.item_name == item_name)
    rows = q.order_by(VersionLedger.id).all()
    return [
        {
            "id": r.id, "version": r.version, "item_name": r.item_name, "item_type": r.item_type,
            "released_at": r.released_at, "executor": r.executor, "change_summary": r.change_summary,
            "review_status": r.review_status, "path": r.path, "file_hash": r.file_hash,
            "is_baseline": r.is_baseline,
        }
        for r in rows
    ]


@router.post("/versions", status_code=status.HTTP_201_CREATED)
def add_version(
    payload: VersionIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """登记版本台账（版本不覆盖：每次登记生成新记录，旧记录永久保留）。"""
    data = payload.model_dump()
    if not data.get("released_at"):
        data["released_at"] = today_str()
    if not data.get("path"):
        data["file_hash"] = ""
    elif not data.get("file_hash"):
        data["file_hash"] = sha256_file(data["path"])
    obj = VersionLedger(**data, project_id=pid)
    db.add(obj)
    db.flush()
    write_log(db, actor=actor.name, action="登记版本台账",
              change=f"{obj.item_name} {obj.version}", artifact_path=obj.path)
    db.commit()
    return {"id": obj.id, "version": obj.version, "item_name": obj.item_name}


@router.post("/versions/{version_id}/baseline")
def promote_baseline(
    version_id: str,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """仅「评审通过」版本可作基线（需求书 §8.4）。"""
    obj = db.get(VersionLedger, version_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="版本记录不存在")
    if obj.review_status != "评审通过":
        raise HTTPException(status_code=409, detail="仅评审通过的版本可基线化")
    obj.is_baseline = True
    write_log(db, actor=actor.name, action="版本基线化", change=f"{obj.item_name} {obj.version}",
              artifact_path=obj.path)
    db.commit()
    return {"id": obj.id, "is_baseline": True}
