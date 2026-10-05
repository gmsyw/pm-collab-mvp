"""流程引擎：8 阶段流水线 + 4 门禁签字（B 流程与门禁域；T11）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import raise_checkpoint, write_log
from ..models import GateRecord, Member, ProcessInstance
from ..schemas import GateSignIn, StageAdvanceIn, TestResultIn
from ..state_machine import (
    GATE_REQUIRED_ON_ADVANCE,
    GATES,
    STAGE_NAMES,
    TEST_EVIDENCE_ON_ADVANCE,
    can_advance_stage,
    gate_for_advance,
    next_stage,
)
from ..utils import utcnow
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api/process", tags=["流程引擎"])


def get_active(db: Session, project_id: str) -> ProcessInstance:
    inst = (
        db.query(ProcessInstance)
        .filter(ProcessInstance.project_id == project_id)
        .order_by(ProcessInstance.created_at.desc())
        .first()
    )
    if inst is None:
        inst = ProcessInstance(name="PM-Collab MVP", milestone="MVP", stage="S1",
                               project_id=project_id)
        db.add(inst)
        db.flush()
        _ensure_gates(db, inst)
        db.commit()
        db.refresh(inst)
    return inst


def _ensure_gates(db: Session, inst: ProcessInstance) -> None:
    for no, name in GATES.items():
        stage = {"①": "S1", "②": "S3", "③": "S5", "④": "S7"}[no]
        if db.query(GateRecord).filter(
            GateRecord.process_id == inst.id, GateRecord.gate_no == no
        ).first():
            continue
        db.add(GateRecord(process_id=inst.id, gate_no=no, gate_name=name, stage=stage))


@router.get("/instance")
def get_instance(
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    inst = get_active(db, pid)
    return {
        "id": inst.id,
        "name": inst.name,
        "milestone": inst.milestone,
        "stage": inst.stage,
        "stage_name": STAGE_NAMES.get(inst.stage, ""),
        "next_stage": next_stage(inst.stage),
        "required_gate": GATE_REQUIRED_ON_ADVANCE.get((inst.stage, next_stage(inst.stage) or "")),
        "test_passed": bool((inst.extra or {}).get("test_passed")),
    }


@router.get("/gates")
def list_gates(
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    """门禁签字台账。"""
    return _gates_payload(db, get_active(db, pid))


def _gates_payload(db: Session, inst: ProcessInstance) -> list[dict]:
    rows = db.query(GateRecord).filter(GateRecord.process_id == inst.id).all()
    return [
        {
            "gate_no": g.gate_no,
            "gate_name": g.gate_name,
            "stage": g.stage,
            "decision": g.decision,
            "signed_by": g.signed_by,
            "signed_at": g.signed_at.isoformat() if g.signed_at else None,
            "opinion": g.opinion,
        }
        for g in sorted(rows, key=lambda x: x.gate_no)
    ]


@router.post("/gates/sign")
def sign_gate(
    payload: GateSignIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """门禁签字——签字权在人类（需求书 §1.4：PM-AI 只判定不代签）。"""
    inst = get_active(db, pid)
    gate = db.query(GateRecord).filter(
        GateRecord.process_id == inst.id, GateRecord.gate_no == payload.gate_no
    ).first()
    if gate is None:
        raise HTTPException(status_code=404, detail="门禁记录不存在")
    if payload.decision == "通过" and actor.member_type != "人类":
        raise HTTPException(status_code=403, detail="门禁签字必须由人类签署（AI 不可代签）")

    gate.decision = payload.decision
    gate.opinion = payload.opinion
    if payload.decision == "通过":
        gate.signed_by = payload.signed_by
        gate.signed_at = utcnow()
    else:
        gate.signed_by = None
        gate.signed_at = None

    write_log(db, actor=actor.name,
              action=f"门禁{payload.gate_no}{GATES.get(payload.gate_no, '')}签字",
              change=f"结论：{payload.decision}" + (f"；意见：{payload.opinion}" if payload.opinion else ""),
              artifact_path="01_项目库/评审记录单/")
    db.commit()
    return {"gate_no": gate.gate_no, "decision": gate.decision, "signed_by": gate.signed_by}


@router.post("/test-result")
def record_test_result(
    payload: TestResultIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    inst = get_active(db, pid)
    extra = dict(inst.extra or {})
    extra["test_passed"] = payload.passed
    extra["test_report_path"] = payload.report_path
    extra["test_recorded_by"] = actor.name
    inst.extra = extra
    write_log(db, actor=actor.name, action="登记测试结果",
              change=f"集成/回归测试 {'通过' if payload.passed else '未通过'}",
              artifact_path=payload.report_path,
              open_issue="" if payload.passed else "测试未通过，不得进入验收（需求书 §7.5）")
    db.commit()
    return {"test_passed": payload.passed}


@router.post("/advance")
def advance_stage(
    payload: StageAdvanceIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """阶段推进：不可跳过、无门禁签字不放行（需求书 §3.1–3.3）。"""
    inst = get_active(db, pid)
    current = inst.stage
    target = payload.target

    if not can_advance_stage(current, target):
        raise HTTPException(
            status_code=409,
            detail=f"阶段不可跳过或倒退：{current} → {target}（下一阶段：{next_stage(current)}）",
        )

    if (current, target) in TEST_EVIDENCE_ON_ADVANCE and not (inst.extra or {}).get("test_passed"):
        raise HTTPException(status_code=422,
                            detail="测试未通过，不得进入验收阶段（需求书 §7.5）")

    gate_no = gate_for_advance(current, target)
    if gate_no:
        gate = db.query(GateRecord).filter(
            GateRecord.process_id == inst.id, GateRecord.gate_no == gate_no
        ).first()
        if gate is None or gate.decision != "通过" or not gate.signed_by:
            raise_checkpoint(
                db, trigger=actor.name, task_code=None, category="审批请求",
                content=f"阶段 {current}→{target} 缺少门禁{gate_no}《{GATES.get(gate_no)}》人类签字",
                human_action=f"完成{GATES.get(gate_no)}评审并在审批台签字后再推进阶段",
                expect_by="本次上线前",
            )
            db.commit()
            raise HTTPException(
                status_code=403,
                detail=f"门禁{gate_no}《{GATES.get(gate_no)}》尚未签字通过，不得放行；已生成审批卡点",
            )

    inst.stage = target
    write_log(db, actor=actor.name, action="阶段推进",
              change=f"{current}（{STAGE_NAMES.get(current)}）→ {target}（{STAGE_NAMES.get(target)}）",
              next_step=f"按 {STAGE_NAMES.get(target)} 阶段准出条件执行")
    db.commit()
    return {"stage": inst.stage, "stage_name": STAGE_NAMES.get(inst.stage)}


@router.get("/checklist")
def checklist(
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    """阶段准出条件自检（需求书 §3.4）。"""
    from ..models import DocEntry, TaskCard

    inst = get_active(db, pid)
    total = db.query(TaskCard).filter(TaskCard.project_id == pid).count()
    closed = db.query(TaskCard).filter(TaskCard.project_id == pid, TaskCard.status == "关闭").count()
    docs = db.query(DocEntry).filter(DocEntry.project_id == pid).count()
    baselines = db.query(DocEntry).filter(DocEntry.project_id == pid, DocEntry.status == "评审通过").count()
    gates = _gates_payload(db, inst)
    return {
        "stage": inst.stage,
        "task_total": total,
        "task_closed": closed,
        "doc_total": docs,
        "doc_baselined": baselines,
        "test_passed": bool((inst.extra or {}).get("test_passed")),
        "gates": gates,
    }
