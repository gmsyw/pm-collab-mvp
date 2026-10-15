"""文档条目 / 版本台账 / 五库托管（E 文档与版本域；T12）。"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import raise_checkpoint, write_log
from ..config import settings
from ..models import DocEntry, Member, VersionLedger
from ..schemas import DocEntryIn, VersionIn
from ..services.five_libs import (
    ensure_project_structure,
    project_code_by_id,
    project_lib_path,
)
from ..utils import TYPE_WORDS, sha256_file, today_str, validate_doc_name
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api", tags=["文档与版本"])

# 五库 → 类型词（文档组织方案 §4.2），用于无 path 时生成合规默认文件名
_LIB_TYPE_WORDS = {
    "01_项目库": "模板",
    "02_需求库": "需求基线",
    "03_设计库": "设计文档",
    "04_测试": "测试报告",
    "05_运维": "发布日志",
}


def _normalize_version(v: str) -> str:
    """归一化为 V主.次.修订（命名规则要求三段），如 V1.0 → V1.0.0。"""
    v = v or "V1.0.0"
    if not v.startswith("V"):
        v = "V" + v
    nums = re.findall(r"\d+", v)
    if not nums:
        return "V1.0.0"
    major = nums[0]
    minor = nums[1] if len(nums) > 1 else "0"
    patch = nums[2] if len(nums) > 2 else "0"
    return f"V{major}.{minor}.{patch}"


def _resolve_doc_path(path: str, project_code: str) -> str:
    """相对路径统一以 data/projects/<code>/ 为基准解析（O-15），保证哈希/校验一致。"""
    if not path:
        return path
    p = Path(path)
    if not p.is_absolute():
        p = Path(settings.data_dir) / "projects" / project_code / path
    return str(p)


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
        if d.name == "projects":  # 各项目独立目录不进入全局五库视图
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
    code = project_code_by_id(db, pid)
    # 用户提供的相对路径统一以项目目录为基准解析（O-15）
    if path:
        path = _resolve_doc_path(path, code)
        data["path"] = path
    # 未给路径时，默认登记到本项目独立目录的对应五库（按 library 归类），
    # 文件名遵循《文档组织方案》§4：项目-类型-名称-V主.次.修订.md
    if not path:
        ensure_project_structure(code)
        library = data.get("library") or "01_项目库"
        category = (data.get("category") or "").strip()
        type_word = category if category in TYPE_WORDS else _LIB_TYPE_WORDS.get(library, "模板")
        version = _normalize_version(data.get("version") or "V1.0.0")
        name = data.get("name") or "未命名"
        default_name = f"{code}-{type_word}-{name}-{version}.md"
        path = str(project_lib_path(code, library) / default_name)
        data["path"] = path
    ok, msg = validate_doc_name(Path(path).name or f"{'-'.join(['PM-Collab', '模板', data['name'], data['version']])}.md")
    if path and not ok:
        raise HTTPException(status_code=422, detail=f"文档命名不合规：{msg}")

    obj = DocEntry(**data, project_id=pid)
    obj.file_hash = sha256_file(path) if path and Path(path).exists() else ""
    try:
        db.add(obj)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"文档编号 {obj.doc_no} 已在本项目存在（项目内唯一）")
    write_log(db, actor=actor.name, action="登记文档条目",
              change=f"{obj.doc_no} {obj.name} {obj.version}", artifact_path=obj.path)
    db.commit()
    return {"id": obj.id, "doc_no": obj.doc_no, "path": obj.path, "file_hash": obj.file_hash}


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


@router.put("/docs/{doc_id}", response_model=dict)
def update_doc(
    doc_id: str,
    payload: DocEntryIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """编辑文档条目（编号不可改；路径合规校验）。"""
    obj = db.get(DocEntry, doc_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="文档条目不存在")
    data = payload.model_dump()
    data.pop("doc_no", None)  # 编号不可改，保可追溯
    if data.get("path"):
        code = project_code_by_id(db, obj.project_id)
        data["path"] = _resolve_doc_path(data["path"], code)
        ok, msg = validate_doc_name(Path(data["path"]).name)
        if not ok:
            raise HTTPException(status_code=422, detail=f"文档命名不合规：{msg}")
    for key, value in data.items():
        setattr(obj, key, value)
    obj.file_hash = sha256_file(obj.path) if obj.path and Path(obj.path).exists() else obj.file_hash
    write_log(db, actor=actor.name, action="编辑文档条目",
              change=f"{obj.doc_no} {obj.name} {obj.version}", artifact_path=obj.path or "")
    db.commit()
    return {"id": obj.id, "doc_no": obj.doc_no, "path": obj.path, "file_hash": obj.file_hash}


@router.delete("/docs/{doc_id}")
def delete_doc(
    doc_id: str,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """删除文档条目（同时尝试删除文件库中的正文文件）。"""
    obj = db.get(DocEntry, doc_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="文档条目不存在")
    path = obj.path
    db.delete(obj)
    write_log(db, actor=actor.name, action="删除文档条目", change=f"{obj.doc_no} {obj.name}",
              artifact_path=path or "")
    db.commit()
    if path:
        try:
            p = Path(path)
            if p.exists() and settings.data_dir in p.parents:
                p.unlink()
        except Exception:
            pass
    return {"deleted": doc_id}


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
