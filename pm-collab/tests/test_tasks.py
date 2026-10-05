"""任务卡 CRUD 与状态机测试（T10）。"""
from __future__ import annotations

TASK = {
    "code": "T-200", "title": "任务卡测试", "goal": "验证状态机", "acceptance": "全部通过",
    "human_owner": "H", "ai_executor": "DEV-AI", "priority": "P1", "due_date": "2026-12-31",
}


def _create(app_client, headers, **over):
    return app_client.post("/api/tasks", json={**TASK, **over}, headers=headers)


def test_create_and_duplicate_and_illegal(app_client, headers):
    r = _create(app_client, headers)
    assert r.status_code == 201 and r.json()["status"] == "待办"
    assert app_client.post("/api/tasks", json=TASK, headers=headers).status_code == 409
    assert _create(app_client, headers, priority="P9").status_code == 422
    assert _create(app_client, headers, bogus=1).status_code == 422


def test_get_and_update(app_client, headers):
    tid = _create(app_client, headers).json()["id"]
    assert app_client.get(f"/api/tasks/{tid}", headers=headers).status_code == 200
    updated = app_client.put(f"/api/tasks/{tid}", json={**TASK, "title": "改后标题"}, headers=headers)
    assert updated.status_code == 200 and updated.json()["title"] == "改后标题"
    assert app_client.get("/api/tasks/not-exist", headers=headers).status_code == 404
    assert app_client.put("/api/tasks/not-exist", json=TASK, headers=headers).status_code == 404


def test_illegal_transition_rejected(app_client, headers):
    tid = _create(app_client, headers).json()["id"]
    r = app_client.post(f"/api/tasks/{tid}/transition", json={"target": "关闭"}, headers=headers)
    assert r.status_code == 409 and "非法状态迁移" in r.json()["detail"]
    r = app_client.post(f"/api/tasks/{tid}/transition", json={"target": "不存在"}, headers=headers)
    assert r.status_code == 422


def test_evidence_required_before_review(app_client, headers):
    tid = _create(app_client, headers).json()["id"]
    assert app_client.post(f"/api/tasks/{tid}/transition", json={"target": "进行中"}, headers=headers).status_code == 200
    r = app_client.post(f"/api/tasks/{tid}/transition", json={"target": "待评审"}, headers=headers)
    assert r.status_code == 422 and "无证据" in r.json()["detail"]

    app_client.post(f"/api/tasks/{tid}/evidence", json={"paths": ["data/evidence.md"]}, headers=headers)
    r = app_client.post(f"/api/tasks/{tid}/transition", json={"target": "待评审"}, headers=headers)
    assert r.status_code == 200
    task = app_client.get(f"/api/tasks/{tid}", headers=headers).json()
    assert task["evidence"] == ["data/evidence.md"]


def test_pass_close_requires_summary_and_rework_flow(app_client, headers):
    tid = _create(app_client, headers).json()["id"]
    h = headers
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "进行中"}, headers=h)
    app_client.post(f"/api/tasks/{tid}/evidence", json={"paths": ["e.md"], "summary": "完成摘要"}, headers=h)
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "待评审"}, headers=h)

    # 返工计数
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "返工"}, headers=h)
    assert app_client.get(f"/api/tasks/{tid}", headers=h).json()["rework_count"] == 1
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "进行中"}, headers=h)
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "待评审"}, headers=h)
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "通过"}, headers=h)
    assert app_client.post(f"/api/tasks/{tid}/transition", json={"target": "关闭"}, headers=h).status_code == 200
    # 终态不可再迁移
    assert app_client.post(f"/api/tasks/{tid}/transition", json={"target": "待办"}, headers=h).status_code == 409


def test_close_without_summary_rejected(app_client, headers):
    tid = _create(app_client, headers).json()["id"]
    h = headers
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "进行中"}, headers=h)
    app_client.post(f"/api/tasks/{tid}/evidence", json={"paths": ["e.md"]}, headers=h)
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "待评审"}, headers=h)
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "通过"}, headers=h)
    r = app_client.post(f"/api/tasks/{tid}/transition", json={"target": "关闭"}, headers=h)
    assert r.status_code == 422 and "完成摘要" in r.json()["detail"]


def test_blocked_requires_reason_and_records_hours(app_client, headers):
    tid = _create(app_client, headers).json()["id"]
    r = app_client.post(f"/api/tasks/{tid}/transition", json={"target": "阻塞"}, headers=headers)
    assert r.status_code == 422 and "阻塞须填写原因" in r.json()["detail"]

    r = app_client.post(f"/api/tasks/{tid}/transition",
                        json={"target": "阻塞", "note": "等待上游接口"}, headers=headers).json()
    assert r["status"] == "阻塞" and r["blocked_reason"] == "等待上游接口"
    assert r["blocked_hours"] >= 0

    ck = app_client.get("/api/checkpoints", params={"status": "待处理"}, headers=headers).json()
    assert any(c["category"] == "决策请求" for c in ck)

    back = app_client.post(f"/api/tasks/{tid}/transition", json={"target": "进行中"}, headers=headers).json()
    assert back["blocked_reason"] is None


def test_review_transition_creates_approval_checkpoint(app_client, headers):
    tid = _create(app_client, headers).json()["id"]
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "进行中"}, headers=headers)
    app_client.post(f"/api/tasks/{tid}/evidence", json={"paths": ["e.md"]}, headers=headers)
    app_client.post(f"/api/tasks/{tid}/transition", json={"target": "待评审"}, headers=headers)
    ck = app_client.get("/api/checkpoints", headers=headers).json()
    assert any(c["category"] == "审批请求" and c["task_code"] == "T-200" for c in ck)


def test_filter_by_status_and_milestone(app_client, headers):
    _create(app_client, headers, code="T-201", milestone="MVP")
    listed = app_client.get("/api/tasks", params={"status": "待办"}, headers=headers).json()
    assert len(listed) == 1
    assert app_client.get("/api/tasks", params={"milestone": "M2"}, headers=headers).json() == []
