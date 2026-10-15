"""API 出入参模型。创建类统一 extra="forbid"——非法字段即被拒（T09/T10 验收）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .state_machine import HANDOFF_STATUS, STAGES, TASK_STATUS

PERMISSION_LEVELS = ("L1", "L2", "L3", "L4")
PRIORITIES = ("P0", "P1", "P2")


class ForbidExtra(BaseModel):
    model_config = ConfigDict(extra="forbid")


def asdict_out(obj: Any) -> dict[str, Any]:
    """ORM → dict 的统一出口（避免外部直接触碰 ORM 对象）。"""
    out: dict[str, Any] = {}
    for col in obj.__table__.columns:
        value = getattr(obj, col.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        out[col.name] = value
    return out


# ---------------- 认证 ----------------
class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


# ---------------- 成员名册 ----------------
class MemberIn(ForbidExtra):
    code: str
    name: str
    member_type: Literal["人类", "AI"]
    status: str = "在岗"
    reports_to: str | None = None
    username: str | None = None
    password: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    member_type: str
    status: str
    reports_to: str | None = None
    project_id: str
    created_at: datetime


# ---------------- 角色卡（8 字段） ----------------
class RoleCardIn(ForbidExtra):
    code: str
    role_type: str = "AI角色"
    duty: str
    negative_list: str = ""
    permission_level: str = "L2"
    data_boundary: str = ""
    reports_to: str | None = None
    downgrade_plan: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("permission_level")
    @classmethod
    def check_level(cls, v: str) -> str:
        if v not in PERMISSION_LEVELS:
            raise ValueError(f"权限等级须为 {PERMISSION_LEVELS} 之一，收到：{v}")
        return v


class RoleCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    role_type: str
    duty: str
    negative_list: str
    permission_level: str
    data_boundary: str
    reports_to: str | None = None
    downgrade_plan: str
    project_id: str


# ---------------- 任务卡（14 字段） ----------------
class TaskCardIn(ForbidExtra):
    code: str
    title: str
    goal: str = ""
    inputs: str = ""
    deliverables: str = ""
    acceptance: str = ""
    human_owner: str = "H"
    ai_executor: str = ""
    dependencies: list[str] = Field(default_factory=list)
    start_date: str | None = None
    due_date: str | None = None
    priority: str = "P2"
    evidence: list[str] = Field(default_factory=list)
    summary: str = ""
    milestone: str = "MVP"  # 冗余展示字段，由 milestone_id 反查填充
    work_package: str = ""  # 冗余展示字段，由 work_package_id 反查填充
    milestone_id: str | None = None
    work_package_id: str | None = None
    parent_task_id: str | None = None  # V0.4：父子任务链
    module_tag: str | None = None  # V0.4：模块标签 S1~S8
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v: str) -> str:
        if v not in PRIORITIES:
            raise ValueError(f"优先级须为 {PRIORITIES} 之一，收到：{v}")
        return v


class TaskTransitionIn(BaseModel):
    target: str
    note: str = ""

    @field_validator("target")
    @classmethod
    def check_status(cls, v: str) -> str:
        if v not in TASK_STATUS:
            raise ValueError(f"状态须为 {TASK_STATUS} 之一，收到：{v}")
        return v


class EvidenceIn(BaseModel):
    paths: list[str]
    summary: str = ""


# ---------------- 交接单 ----------------
class HandoffIn(ForbidExtra):
    code: str
    sender: str = "PM-AI"
    receiver: str = ""
    zone: str = "派单"
    payload_path: str = ""
    task_code: str | None = None
    event_type: str = ""  # V0.4：结构化事件类型
    round: int = 0  # V0.4：评审轮次
    evidence: dict[str, Any] = Field(default_factory=dict)  # V0.4：QA 证据
    extra: dict[str, Any] = Field(default_factory=dict)


class HandoffTransitionIn(BaseModel):
    target: str

    @field_validator("target")
    @classmethod
    def check(cls, v: str) -> str:
        if v not in HANDOFF_STATUS:
            raise ValueError(f"交接状态须为 {HANDOFF_STATUS} 之一，收到：{v}")
        return v


# ---------------- 卡点信号 ----------------
class CheckpointIn(BaseModel):
    trigger: str = "PM-AI"
    content: str
    human_action: str
    expect_by: str | None = None
    task_code: str | None = None
    category: str = "搬运请求"


class CheckpointHandleIn(BaseModel):
    note: str = ""


# ---------------- 文档条目 / 版本台账 ----------------
class DocEntryIn(ForbidExtra):
    doc_no: str
    library: str = "01_项目库"
    category: str = ""
    name: str
    version: str = "V1.0.0"
    owner: str = ""
    status: str = "草稿"
    path: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class VersionIn(ForbidExtra):
    version: str
    item_name: str
    item_type: str = ""
    executor: str = ""
    change_summary: str = ""
    change_ticket: str | None = None
    review_status: str = "草稿"
    path: str = ""
    file_hash: str = ""
    is_baseline: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------- 需求条目 / 追加日志 ----------------
class RequirementIn(ForbidExtra):
    code: str
    section: str = ""
    content: str
    review_status: str = "待评审"
    priority: str = "P1"
    in_mvp: bool = False
    trace_links: list[str] = Field(default_factory=list)


class AppendLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    occurred_at: datetime
    actor: str
    action: str
    artifact_path: str
    change: str
    next_step: str
    open_issue: str


# ---------------- WBS：里程碑 / 工作包 / 子任务 ----------------
class MilestoneIn(ForbidExtra):
    code: str
    name: str
    description: str = ""
    status: str = "进行中"
    owner: str = ""
    start_date: str | None = None
    due_date: str | None = None
    order_index: int = 0


class WorkPackageIn(ForbidExtra):
    milestone_id: str
    code: str
    name: str
    description: str = ""
    status: str = "进行中"
    owner: str = ""
    start_date: str | None = None
    due_date: str | None = None
    order_index: int = 0


class SubTaskIn(ForbidExtra):
    task_id: str
    code: str
    title: str
    description: str = ""
    status: str = "待办"
    assignee: str = ""
    priority: str = "P2"
    due_date: str | None = None
    order_index: int = 0

    @field_validator("status")
    @classmethod
    def check_status(cls, v: str) -> str:
        if v not in TASK_STATUS:
            raise ValueError(f"状态须为 {TASK_STATUS} 之一，收到：{v}")
        return v

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v: str) -> str:
        if v not in PRIORITIES:
            raise ValueError(f"优先级须为 {PRIORITIES} 之一，收到：{v}")
        return v


class SubTaskTransitionIn(BaseModel):
    target: str

    @field_validator("target")
    @classmethod
    def check_status(cls, v: str) -> str:
        if v not in TASK_STATUS:
            raise ValueError(f"状态须为 {TASK_STATUS} 之一，收到：{v}")
        return v


class SubTaskEvidenceIn(BaseModel):
    paths: list[str]
    summary: str = ""


# ---------------- 项目（WBS 根实体） ----------------
class ProjectIn(ForbidExtra):
    code: str
    name: str
    description: str = ""
    owner: str = ""


class ProjectUpdateIn(ForbidExtra):
    """项目编辑：仅更新传入字段（编号不可改，即便传入也会被忽略）。"""

    code: str | None = None  # 占位，更新时被忽略
    name: str | None = None
    description: str | None = None
    owner: str | None = None
    status: str | None = None


# ---------------- 流程与门禁 ----------------
class StageAdvanceIn(BaseModel):
    target: str

    @field_validator("target")
    @classmethod
    def check(cls, v: str) -> str:
        if v not in STAGES:
            raise ValueError(f"阶段须为 {STAGES} 之一，收到：{v}")
        return v


class GateSignIn(BaseModel):
    gate_no: Literal["①", "②", "③", "④"]
    decision: Literal["通过", "驳回"] = "通过"
    signed_by: str = "H"
    opinion: str = ""


class TestResultIn(BaseModel):
    passed: bool
    report_path: str = ""
    note: str = ""
