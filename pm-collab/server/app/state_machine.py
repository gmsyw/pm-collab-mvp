"""状态机定义：任务卡 / 交接单 / 流程阶段与门禁。

全部集中在服务层，非法迁移在 API 入口即被拒绝（MVP DoD 第 2 条）。
来源：需求规格书 §3.1、§4.3；MVP 任务分解 §1.1；通用方法 §4。
"""
from __future__ import annotations

# ---------------- 任务卡状态机（需求书 §4.3） ----------------
TASK_STATUS = (
    "待办",
    "进行中",
    "待评审",
    "通过",
    "返工",
    "关闭",
    "阻塞",
    "取消",
)

TASK_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "待办": ("进行中", "阻塞", "取消"),
    "进行中": ("待评审", "阻塞", "取消"),
    "待评审": ("通过", "返工", "阻塞"),
    "通过": ("关闭",),
    "返工": ("进行中", "阻塞", "取消"),
    "阻塞": ("进行中", "取消"),
    "关闭": (),
    "取消": (),
}

# 需要证据才能置位的状态（需求书 §5.3 无证据不得置为"通过"）
EVIDENCE_REQUIRED_STATUS = ("待评审", "通过", "关闭")
# 需要完成摘要的状态（需求书 §4.7）
SUMMARY_REQUIRED_STATUS = ("关闭",)


def can_transit_task(current: str, target: str) -> bool:
    return target in TASK_TRANSITIONS.get(current, ())


# ---------------- 交接单状态机（通用方法 §4） ----------------
HANDOFF_STATUS = ("待投喂", "已投喂", "已回收", "已闭环")

HANDOFF_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "待投喂": ("已投喂",),
    "已投喂": ("已回收",),
    "已回收": ("已闭环",),
    "已闭环": (),
}


def can_transit_handoff(current: str, target: str) -> bool:
    return target in HANDOFF_TRANSITIONS.get(current, ())


# ---------------- 8 阶段流水线与 4 门禁（需求书 §3.1/§3.3） ----------------
STAGES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")

STAGE_NAMES = {
    "S1": "需求录入",
    "S2": "设计",
    "S3": "设计评审",
    "S4": "开发",
    "S5": "代码评审",
    "S6": "测试",
    "S7": "验收",
    "S8": "归档",
}

GATES = {
    "①": "需求评审",
    "②": "设计评审",
    "③": "代码评审",
    "④": "验收",
}

# 阶段推进所需门禁签字：无门禁签字不放行（设计大纲 §1.2）
GATE_REQUIRED_ON_ADVANCE: dict[tuple[str, str], str] = {
    ("S1", "S2"): "①",
    ("S3", "S4"): "②",
    ("S5", "S6"): "③",
    ("S7", "S8"): "④",
}

# 测试不通过不得进入验收（需求书 §7.5）
TEST_EVIDENCE_ON_ADVANCE: set[tuple[str, str]] = {("S6", "S7")}


def next_stage(stage: str) -> str | None:
    if stage not in STAGES:
        return None
    idx = STAGES.index(stage)
    return STAGES[idx + 1] if idx + 1 < len(STAGES) else None


def can_advance_stage(current: str, target: str) -> bool:
    return target == next_stage(current)


def gate_for_advance(current: str, target: str) -> str | None:
    return GATE_REQUIRED_ON_ADVANCE.get((current, target))
