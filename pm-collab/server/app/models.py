"""PM-Collab 数据模型（MVP 10 张主表 + 流程/门禁 2 张引擎表）。

对应《人机共用项目管理软件-设计大纲 V0.3》§4 核心数据实体（12 类），
MVP 落地 10 张主表；评审意见、缺陷两张表按 MVP 任务分解 §2 后置 M2。
存储约定：结构化记录落 PostgreSQL/SQLite，文件正文留在文件库（五库/交接区），
PG 表仅存路径引用 + 哈希，遵循"一次一处"。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# JSONB 承载任务卡/交接单/卡点半结构化扩展字段；SQLite 降级为 JSON
JsonType = JSONB().with_variant(JSON, "sqlite")

# 默认项目（MVP 单项目优先，但数据层预留多项目能力；需求书 §4.1 / 设计大纲决策点④）
DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000001"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Project(Base, TimestampMixin):
    """项目：WBS 根实体（需求书 §4.1：项目→里程碑→工作包→任务；

    设计大纲决策点④：单项目优先，数据结构预留多项目。
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="进行中")  # 进行中/已归档
    owner: Mapped[str] = mapped_column(String(128), default="")
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class Member(Base, TimestampMixin):
    """01 成员名册：人与 AI 成员统一建档、统一编号。"""

    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # 成员编号
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    member_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 人类 / AI
    status: Mapped[str] = mapped_column(String(16), default="在岗")  # 在岗/停用
    reports_to: Mapped[str | None] = mapped_column(String(36), nullable=True)  # 汇报对象成员 ID
    username: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 改密后旧 token 吊销（OSS-02）：NULL=不限制；改密时写入时间戳，
    # iat 早于该时间的 JWT 一律 401（无状态吊销，单机零开销）。
    token_valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # MVP 单用户；保留多用户扩展字段。默认归属规范化为 DEFAULT_PROJECT_ID（不再用字面量 "default"）
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID)
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class RoleCard(Base, TimestampMixin):
    """02 角色卡：8 字段（设计大纲 §4 / 需求规格书 §2.4）。"""

    __tablename__ = "role_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 人类角色/AI角色
    duty: Mapped[str] = mapped_column(Text, nullable=False)  # 职责
    negative_list: Mapped[str] = mapped_column(Text, default="")  # 负面清单
    permission_level: Mapped[str] = mapped_column(String(8), default="L2")  # L1–L4
    data_boundary: Mapped[str] = mapped_column(Text, default="")  # 数据与工具边界
    reports_to: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 汇报对象
    downgrade_plan: Mapped[str] = mapped_column(Text, default="")  # 降级预案
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class TaskCard(Base, TimestampMixin):
    """03 任务卡：14 字段（需求规格书 §4.2）。"""

    __tablename__ = "task_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False)
    # 编号唯一性：项目内唯一（需求书 §4.1），跨项目允许复用 —— 复合唯一 (project_id, code)
    code: Mapped[str] = mapped_column(String(64), nullable=False)  # T01…
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_taskcard_project_code"),
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)  # 目标/标题
    goal: Mapped[str] = mapped_column(Text, default="")  # 目标详述
    inputs: Mapped[str] = mapped_column(Text, default="")  # 输入
    deliverables: Mapped[str] = mapped_column(Text, default="")  # 交付物及路径
    acceptance: Mapped[str] = mapped_column(Text, default="")  # 验收标准
    human_owner: Mapped[str] = mapped_column(String(128), default="H")  # 人类负责人 人-A
    ai_executor: Mapped[str] = mapped_column(String(128), default="")  # AI 执行者 AI-R
    dependencies: Mapped[list] = mapped_column(JsonType, default=list)  # 依赖任务编号
    start_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    priority: Mapped[str] = mapped_column(String(8), default="P2")  # P0/P1/P2
    status: Mapped[str] = mapped_column(String(16), default="待办", index=True)
    evidence: Mapped[list] = mapped_column(JsonType, default=list)  # 证据路径列表
    summary: Mapped[str] = mapped_column(Text, default="")  # 完成摘要
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # 阻塞原因
    blocked_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    milestone: Mapped[str] = mapped_column(String(64), default="MVP")
    work_package: Mapped[str] = mapped_column(String(64), default="")
    rework_count: Mapped[int] = mapped_column(Integer, default=0)
    # WBS 层级关联（需求书 §4.1：项目→里程碑→工作包→任务；任务下再拆子任务）
    milestone_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    work_package_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # V0.4 新增：父子任务链（详设→开发→QA→合入四子任务链）
    parent_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # V0.4 新增：模块标签 S1~S8（模块泳道视图聚合键）
    module_tag: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class Milestone(Base, TimestampMixin):
    """WBS 第二层：里程碑（需求书 §4.1）。

    一个项目可含多个里程碑；工作包归属于里程碑，任务归属于工作包。
    """

    __tablename__ = "milestones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)  # M1 / MVP
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="进行中")  # 进行中/已完成/已归档
    owner: Mapped[str] = mapped_column(String(128), default="")
    start_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class WorkPackage(Base, TimestampMixin):
    """WBS 第三层：工作包（需求书 §4.1）。

    隶属于里程碑；任务归属于工作包。
    """

    __tablename__ = "work_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False, index=True)
    milestone_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)  # WP0
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="进行中")
    owner: Mapped[str] = mapped_column(String(128), default="")
    start_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class SubTask(Base, TimestampMixin):
    """WBS 第五层：任务下的子任务（需求书 §4.1 之上的细化层）。

    任务（TaskCard）可向下拆解一层子任务，用于更细粒度的执行跟踪。
    子任务状态机复用任务卡状态机（state_machine.TASK_STATUS）。
    """

    __tablename__ = "sub_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)  # ST-...
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="待办")
    assignee: Mapped[str] = mapped_column(String(128), default="")
    priority: Mapped[str] = mapped_column(String(8), default="P2")
    due_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence: Mapped[list] = mapped_column(JsonType, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class HandoffOrder(Base, TimestampMixin):
    """04 交接单：与交接区 JSON 文件双向同步，4 态状态机。"""

    __tablename__ = "handoff_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # HO-001
    sender: Mapped[str] = mapped_column(String(128), default="")  # 发起方
    receiver: Mapped[str] = mapped_column(String(128), default="")  # 接收方
    zone: Mapped[str] = mapped_column(String(32), default="派单")  # 交接区子目录
    payload_path: Mapped[str] = mapped_column(Text, default="")  # 载体路径
    status: Mapped[str] = mapped_column(String(16), default="待投喂", index=True)
    task_code: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 关联任务
    fed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recycled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # V0.4 新增：结构化事件字段（M3 起新建交接单强制填写；迁移数据由服务层正则推断）
    event_type: Mapped[str] = mapped_column(String(32), default="")  # 派单/开发交付/评审意见/修订返工/QA通过/签字/合入
    round: Mapped[int] = mapped_column(Integer, default=0)  # 评审轮次
    evidence: Mapped[dict] = mapped_column(JsonType, default=dict)  # QA 用例数/覆盖率/缺陷数等
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class CheckpointSignal(Base, TimestampMixin):
    """05 卡点信号：6 字段（通用方法 §7）。"""

    __tablename__ = "checkpoint_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False  # ① 发生时间
    )
    trigger: Mapped[str] = mapped_column(String(128), default="")  # ② 触发者
    content: Mapped[str] = mapped_column(Text, default="")  # ③ 卡点内容
    human_action: Mapped[str] = mapped_column(Text, default="")  # ④ 人类需要做什么
    expect_by: Mapped[str | None] = mapped_column(String(64), nullable=True)  # ⑤ 期望时限
    task_code: Mapped[str | None] = mapped_column(String(64), nullable=True)  # ⑥ 关联任务
    category: Mapped[str] = mapped_column(String(32), default="搬运请求")
    status: Mapped[str] = mapped_column(String(16), default="待处理", index=True)  # 待处理/已处理
    handled_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class DocEntry(Base, TimestampMixin):
    """06 文档条目：五库文件登记（路径 + 哈希，正文不入库）。"""

    __tablename__ = "doc_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False)
    # 编号唯一性：项目内唯一（需求书 §4.1），跨项目允许复用 —— 复合唯一 (project_id, doc_no)
    doc_no: Mapped[str] = mapped_column(String(64), nullable=False)  # 唯一编号
    library: Mapped[str] = mapped_column(String(16), default="01_项目库")  # 五库归属
    category: Mapped[str] = mapped_column(String(64), default="")  # 类型
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str] = mapped_column(String(16), default="V1.0")
    owner: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="草稿")  # 草稿/待评审/评审通过/归档
    path: Mapped[str] = mapped_column(Text, default="")
    file_hash: Mapped[str] = mapped_column(String(128), default="")
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)

    __table_args__ = (
        UniqueConstraint("project_id", "doc_no", name="uq_doc_entries_project_docno"),
    )


class VersionLedger(Base, TimestampMixin):
    """07 版本台账：版本号/日期/执行者/变更摘要/变更单/评审状态/路径/哈希。"""

    __tablename__ = "version_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    item_name: Mapped[str] = mapped_column(String(256), nullable=False)
    item_type: Mapped[str] = mapped_column(String(64), default="")
    released_at: Mapped[str] = mapped_column(String(32), default="")
    executor: Mapped[str] = mapped_column(String(128), default="")
    change_summary: Mapped[str] = mapped_column(Text, default="")
    change_ticket: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_status: Mapped[str] = mapped_column(String(16), default="草稿")
    path: Mapped[str] = mapped_column(Text, default="")
    file_hash: Mapped[str] = mapped_column(String(128), default="")
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class AppendLog(Base):
    """08 追加日志：只增不改、不可删除（触发器 + REVOKE 强制，见迁移 T06）。

    注意：本表无 updated_at —— 任何更新在库层即被拒绝。
    """

    __tablename__ = "append_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)  # 时间
    actor: Mapped[str] = mapped_column(String(128), default="")  # 执行者
    action: Mapped[str] = mapped_column(String(256), default="")  # 动作
    artifact_path: Mapped[str] = mapped_column(Text, default="")  # 产出物路径
    change: Mapped[str] = mapped_column(Text, default="")  # 变更
    next_step: Mapped[str] = mapped_column(Text, default="")  # 下一步
    open_issue: Mapped[str] = mapped_column(Text, default="")  # 遗留问题
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class RequirementItem(Base, TimestampMixin):
    """09 需求条目：需求规格书条目化后的种子库（可追溯）。"""

    __tablename__ = "requirement_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # R-3.2.1
    source_doc: Mapped[str] = mapped_column(String(128), default="需求规格书 V1.0")
    section: Mapped[str] = mapped_column(String(64), default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="待评审")
    priority: Mapped[str] = mapped_column(String(8), default="P1")
    in_mvp: Mapped[bool] = mapped_column(Boolean, default=False)
    trace_links: Mapped[list] = mapped_column(JsonType, default=list)  # 追溯链接
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class MetricRecord(Base, TimestampMixin):
    """10 度量记录：每日摘要数据源（4 指标）。"""

    __tablename__ = "metric_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False)
    period: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # YYYY-MM-DD
    on_time_rate: Mapped[float] = mapped_column(default=0.0)  # 按期率
    rework_rate: Mapped[float] = mapped_column(default=0.0)  # 返工率
    ai_adoption_rate: Mapped[float] = mapped_column(default=0.0)  # AI 产出采纳率
    review_close_rate: Mapped[float] = mapped_column(default=0.0)  # 评审问题关闭率
    task_total: Mapped[int] = mapped_column(Integer, default=0)
    task_closed: Mapped[int] = mapped_column(Integer, default=0)
    overdue_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    summary_text: Mapped[str] = mapped_column(Text, default="")
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class ProcessInstance(Base, TimestampMixin):
    """流程实例：8 阶段流水线（需求规格书 §3.1），阶段不可跳过。"""

    __tablename__ = "process_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="PM-Collab MVP")
    milestone: Mapped[str] = mapped_column(String(32), default="MVP")
    stage: Mapped[str] = mapped_column(String(16), default="S1", index=True)
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)


class GateRecord(Base, TimestampMixin):
    """门禁签字记录：4 门禁必须由人类签字（PM-AI 只判定不代签）。"""

    __tablename__ = "gate_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_PROJECT_ID, nullable=False)
    process_id: Mapped[str] = mapped_column(String(36), default="")
    gate_no: Mapped[str] = mapped_column(String(8), nullable=False)  # ①②③④
    gate_name: Mapped[str] = mapped_column(String(64), default="")
    stage: Mapped[str] = mapped_column(String(16), default="")
    signed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 人类签字
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), default="待审核")  # 待审核/通过/驳回
    opinion: Mapped[str] = mapped_column(Text, default="")
    extra: Mapped[dict] = mapped_column(JsonType, default=dict)
