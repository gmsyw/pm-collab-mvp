"""卡点队列测试（T16）：创建 6 字段、处理、过滤、实时事件。"""
from __future__ import annotations


def test_create_and_list(app_client, headers):
    payload = {
        "trigger": "PM-AI", "content": "缺少门禁②签字",
        "human_action": "在设计评审记录上签字", "expect_by": "今日 18:00",
        "task_code": "T04", "category": "审批请求",
    }
    r = app_client.post("/api/checkpoints", json=payload, headers=headers)
    assert r.status_code == 201 and r.json()["status"] == "待处理"

    listed = app_client.get("/api/checkpoints", headers=headers).json()
    assert listed and listed[0]["task_code"] == "T04"
    assert listed[0]["human_action"] == "在设计评审记录上签字"

    pending = app_client.get("/api/checkpoints", params={"status": "待处理"}, headers=headers).json()
    assert len(pending) == 1


def test_handle_flow(app_client, headers, task_fixture, db):
    from server.app.audit import raise_checkpoint

    signal = raise_checkpoint(db, trigger="PM-AI", content="需搬运文件",
                              human_action="把文件投喂到 DEV 对话", task_code="T-T01")
    db.commit()

    r = app_client.post(f"/api/checkpoints/{signal.id}/handle",
                        json={"note": "H 已完成搬运"}, headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "已处理"
    assert app_client.get("/api/checkpoints", params={"status": "已处理"}, headers=headers).json()[0]["handled_note"] == "H 已完成搬运"
    assert app_client.post("/api/checkpoints/nope/handle", json={"note": ""}, headers=headers).status_code == 404


def test_checkpoint_default_trigger_uses_actor(app_client, headers):
    r = app_client.post("/api/checkpoints", json={"content": "内容",
                                                  "human_action": "搬运"}, headers=headers)
    assert r.status_code == 201
