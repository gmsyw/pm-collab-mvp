"""流程引擎：8 阶段流水线 + 4 门禁签字（B 流程与门禁域；T11）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import raise_checkpoint, write_log
from ..models import GateRecord, Member, ProcessInstance
from ..schemas import GateSignIn, StageAdvanceIn, TestResultIn
from ..state_machine import (
    GATE_REQUIRED_ON_ADVANCE,
    GATES,
    STAGES,
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
                db, trigger=actor.name, task_code=None, project_id=pid, category="审批请求",
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


# ---------------- 阶段操作指引（人类与 AI 共用同一份"现在该做什么"） ----------------
# 来源：需求规格书 §3.1–3.4、§7.5；设计大纲 §1.2、§5.2。
# 人类前台与 AI（持 JWT 调本接口）拿到的是同一份指引，避免人机各做各的。
STAGE_GUIDE: dict[str, dict[str, Any]] = {
    "S1": {
        "goal": "录入需求并形成需求基线",
        "human": [
            "在「文档与版本」登记需求基线文档到 01_项目库/需求基线/",
            "组织需求评审，确认需求范围与验收标准",
            "在「流程与门禁」签署门禁①《需求评审》（签字权专属人类）",
        ],
        "ai": [
            "（可选）协助梳理需求条目、拆分验收标准",
            "对含糊需求提出澄清问题——参数缺失只问不猜",
        ],
        "exit": ["需求基线文档已登记", "门禁①《需求评审》人类签字通过"],
    },
    "S2": {
        "goal": "完成方案与技术设计，产出设计文档",
        "human": [
            "指派设计负责人，确认设计范围与约束条件",
            "审阅 AI 产出的设计文档与方案取舍",
        ],
        "ai": [
            "依据需求基线产出设计文档到 02_交付物/02_设计/",
            "列出方案取舍、风险与待确认项",
        ],
        "exit": ["设计文档已登记并含取舍说明", "可进入设计评审"],
    },
    "S3": {
        "goal": "评审设计并签字放行",
        "human": [
            "评审设计文档，记录评审意见",
            "在「流程与门禁」签署门禁②《设计评审》",
        ],
        "ai": [
            "依据评审意见修订设计文档",
            "补充评审记录单到 01_项目库/评审记录单/",
        ],
        "exit": ["门禁②《设计评审》人类签字通过"],
    },
    "S4": {
        "goal": "按设计实现交付物（人机协作主战场）",
        "human": [
            "首次派单前：在「成员名册」建 AI 成员，在「角色卡」为其定义职责与边界",
            "在「任务卡」创建任务并指派，点「投喂」把任务写入交接区 派单/",
            "在「交接区与卡点」处理 AI 抛出的卡点信号",
        ],
        "ai": [
            "从交接区 派单/ 领取任务，先写 回执/ 复述交付物与验收标准",
            "完成后写回 完成/ 目录（含 任务编号 / 执行者 / 证据路径 / 交付路径 / 版本）",
            "遇阻塞或缺参数抛卡点，不擅自猜测，不代人类签字",
        ],
        "exit": ["任务卡完成且证据齐备", "完成摘要已填写", "可进入代码评审"],
    },
    "S5": {
        "goal": "评审代码与证据并签字放行",
        "human": [
            "评审代码与证据包，记录评审意见",
            "在「流程与门禁」签署门禁③《代码评审》",
        ],
        "ai": [
            "依据评审意见返工并重新提交",
            "补齐证据路径与完成摘要",
        ],
        "exit": ["门禁③《代码评审》人类签字通过"],
    },
    "S6": {
        "goal": "执行集成/回归测试并通过",
        "human": [
            "执行或确认测试，在「流程与门禁」登记测试结果（通过 / 未通过）",
            "测试未通过则退回修复，不得进入验收",
        ],
        "ai": [
            "生成测试用例与测试报告到 02_交付物/04_测试/",
            "修复缺陷并重测，更新证据",
        ],
        "exit": ["测试结果登记为「通过」（未通过不得进入 S7 验收）"],
    },
    "S7": {
        "goal": "验收交付物并签字放行",
        "human": [
            "按验收标准验收交付物",
            "在「流程与门禁」签署门禁④《验收》",
        ],
        "ai": ["整理验收材料与证据包，配合答疑"],
        "exit": ["门禁④《验收》人类签字通过"],
    },
    "S8": {
        "goal": "基线化版本并完成归档",
        "human": [
            "在「文档与版本」将评审通过的版本提升为基线",
            "归档项目资料到 05_版本库/archive/",
        ],
        "ai": ["生成归档清单与发布日志"],
        "exit": ["版本已基线化", "项目资料归档完成"],
    },
}


@router.get("/guide")
def guide(
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    """项目进程指引：阶段目标、人机各自职责、准出条件、阻塞项与下一步动作。"""
    from ..models import CheckpointSignal, DocEntry, Milestone, RoleCard, TaskCard

    inst = get_active(db, pid)
    cur = inst.stage
    nxt = next_stage(cur)
    idx = STAGES.index(cur) if cur in STAGES else 0
    g = STAGE_GUIDE.get(cur, {})

    gates = {r.gate_no: r for r in
             db.query(GateRecord).filter(GateRecord.process_id == inst.id).all()}
    need_gate = gate_for_advance(cur, nxt) if nxt else None
    gate_signed = bool(
        need_gate and gates.get(need_gate)
        and gates[need_gate].decision == "通过" and gates[need_gate].signed_by
    )
    need_test = bool(nxt and (cur, nxt) in TEST_EVIDENCE_ON_ADVANCE)
    test_ok = bool((inst.extra or {}).get("test_passed"))

    # 下一步动作：先解阻塞（签字 / 测试），都满足才允许推进
    if nxt is None:
        next_action = {"type": "archive", "label": "已到最终阶段：基线化版本并归档", "to": "/docs"}
    elif need_gate and not gate_signed:
        next_action = {
            "type": "sign_gate", "gate_no": need_gate,
            "label": f"人类签署门禁{need_gate}《{GATES.get(need_gate)}》",
            "to": "/governance",
        }
    elif need_test and not test_ok:
        next_action = {"type": "record_test",
                       "label": "登记测试结果（须「通过」才可进入验收）", "to": "/governance"}
    else:
        next_action = {"type": "advance", "target": nxt,
                       "label": f"推进到 {nxt} {STAGE_NAMES.get(nxt, '')}", "to": "/governance"}

    # 口径与 members/roles 列表一致：本项目成员 + 全局默认成员（历史成员 project_id="default"）
    scope = [pid, "default"]
    members_n = db.query(Member).filter(Member.project_id.in_(scope)).count()
    ai_n = db.query(Member).filter(
        Member.project_id.in_(scope), Member.member_type == "AI").count()
    roles_n = db.query(RoleCard).filter(RoleCard.project_id.in_(scope)).count()
    docs_n = db.query(DocEntry).filter(DocEntry.project_id == pid).count()
    base_n = db.query(DocEntry).filter(
        DocEntry.project_id == pid, DocEntry.status == "评审通过").count()
    tasks_n = db.query(TaskCard).filter(TaskCard.project_id == pid).count()
    closed_n = db.query(TaskCard).filter(
        TaskCard.project_id == pid, TaskCard.status == "关闭").count()
    ms_n = db.query(Milestone).filter(Milestone.project_id == pid).count()
    cp_n = db.query(CheckpointSignal).filter(
        CheckpointSignal.project_id == pid, CheckpointSignal.status == "待处理").count()

    return {
        "stage": cur,
        "stage_name": STAGE_NAMES.get(cur, ""),
        "next_stage": nxt,
        "next_stage_name": STAGE_NAMES.get(nxt, "") if nxt else "",
        "progress": {
            "index": idx,
            "total": len(STAGES),
            "percent": round(idx / (len(STAGES) - 1) * 100) if len(STAGES) > 1 else 0,
        },
        "stages": [
            {
                "key": s,
                "name": STAGE_NAMES.get(s, ""),
                "state": "done" if STAGES.index(s) < idx else ("current" if s == cur else "todo"),
            }
            for s in STAGES
        ],
        "goal": g.get("goal", ""),
        "human_actions": g.get("human", []),
        "ai_actions": g.get("ai", []),
        "exit_criteria": g.get("exit", []),
        "blockers": {
            "need_gate": need_gate,
            "gate_name": GATES.get(need_gate, "") if need_gate else "",
            "gate_signed": gate_signed,
            "need_test": need_test,
            "test_passed": test_ok,
        },
        "next_action": next_action,
        "open_checkpoints": cp_n,
        "readiness": {
            "members": members_n,
            "ai_members": ai_n,
            "roles": roles_n,
            "milestones": ms_n,
            "tasks": tasks_n,
            "closed_tasks": closed_n,
            "docs": docs_n,
            "baselined_docs": base_n,
        },
    }
