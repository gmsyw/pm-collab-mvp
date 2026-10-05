"""纯函数单元测试：状态机与命名校验。"""
from __future__ import annotations

from server.app.state_machine import (
    can_advance_stage, can_transit_handoff, can_transit_task,
    gate_for_advance, next_stage,
)
from server.app.utils import sha256_file, sha256_text, validate_doc_name


def test_task_transitions():
    assert can_transit_task("待办", "进行中")
    assert can_transit_task("待评审", "通过")
    assert can_transit_task("待评审", "返工")
    assert not can_transit_task("待办", "关闭")  # 跳跃被拒
    assert not can_transit_task("关闭", "待办")  # 终态不可回退
    assert not can_transit_task("取消", "进行中")


def test_handoff_transitions_linear():
    assert can_transit_handoff("待投喂", "已投喂")
    assert can_transit_handoff("已投喂", "已回收")
    assert can_transit_handoff("已回收", "已闭环")
    assert not can_transit_handoff("待投喂", "已闭环")  # 不可跳过
    assert not can_transit_handoff("已闭环", "已投喂")  # 终态不可逆


def test_stage_flow_and_gates():
    assert next_stage("S1") == "S2"
    assert can_advance_stage("S1", "S2")
    assert not can_advance_stage("S1", "S3")  # 阶段不可跳过
    assert gate_for_advance("S1", "S2") == "①"
    assert gate_for_advance("S7", "S8") == "④"
    assert gate_for_advance("S2", "S3") is None
    assert next_stage("S8") is None


def test_doc_naming():
    ok, _ = validate_doc_name("PM-Collab-设计文档-数据模型-V1.0.0.md")
    assert ok
    bad, msg = validate_doc_name("需求说明最新版.docx")
    assert not bad
    assert "命名格式" in msg
    bad2, msg2 = validate_doc_name("PM-Collab-未知类型-名称-V1.0.0.md")
    assert not bad2 and "类型词" in msg2
    bad3, _ = validate_doc_name("PM-Collab-设计文档-名称-V1.0.md")  # 版本号须三位
    assert not bad3


def test_hash(data_dir):
    p = data_dir / "hash-sample.txt"
    p.write_text("hello", encoding="utf-8")
    assert sha256_file(p) == sha256_text("hello")
    assert sha256_file(data_dir / "missing.txt") == ""
    assert sha256_file(data_dir) == ""  # 目录不参与哈希
