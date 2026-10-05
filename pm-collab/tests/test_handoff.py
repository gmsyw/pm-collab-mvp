"""交接总线测试（T13/T14/T15）：投喂→回写→回收→台账 端到端。"""
from __future__ import annotations

import json
from pathlib import Path

TASK = {"code": "T-T14", "title": "交接任务", "ai_executor": "DEV-AI", "acceptance": "闭环"}


def _task(app_client, headers):
    return app_client.post("/api/tasks", json=TASK, headers=headers).json()


def test_zone_directories_ready(app_client, headers):
    zones = app_client.get("/api/handoff/zones", headers=headers).json()["files"]
    assert set(zones) == {"派单", "回执", "完成", "评审输入", "评审输出", "卡点"}


def test_order_create_and_illegal_transition(app_client, headers):
    r = app_client.post("/api/handoff", json={"code": "HO-1", "receiver": "DEV-AI",
                                              "task_code": "T-T14"}, headers=headers)
    assert r.status_code == 201 and r.json()["status"] == "待投喂"
    oid = r.json()["id"]

    assert app_client.post("/api/handoff", json={"code": "HO-1"}, headers=headers).status_code == 409
    r = app_client.post(f"/api/handoff/{oid}/transition", json={"target": "已闭环"}, headers=headers)
    assert r.status_code == 409  # 不可跳过中间态
    r = app_client.post(f"/api/handoff/{oid}/transition", json={"target": "已投喂"}, headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "已投喂"
    r = app_client.post(f"/api/handoff/{oid}/transition", json={"target": "已回收"}, headers=headers)
    assert r.json()["status"] == "已回收"
    r = app_client.post(f"/api/handoff/{oid}/transition", json={"target": "已闭环"}, headers=headers)
    assert r.json()["status"] == "已闭环"
    assert app_client.post(f"/api/handoff/{oid}/transition", json={"target": "已投喂"},
                           headers=headers).status_code == 409
    assert app_client.post(f"/api/handoff/not-exist/transition", json={"target": "已投喂"},
                           headers=headers).status_code == 404


def test_feed_recycle_close_end_to_end(app_client, headers, data_dir):
    task = _task(app_client, headers)
    feed = app_client.post(f"/api/handoff/feed/{task['id']}",
                           params={"receiver": "DEV-AI"}, headers=headers).json()
    assert feed["status"] == "已投喂"
    feed_path = Path(feed["file"])
    assert feed_path.exists() and feed_path.parent.name == "派单"
    assert "任务卡 T-T14" in feed_path.read_text(encoding="utf-8")

    order = app_client.get("/api/handoff", headers=headers).json()[0]

    # 接收方回写「完成/」
    done_dir = feed_path.parent.parent / "完成"
    (done_dir / "T-T14_完成_交接任务_V1.md").write_text(
        "任务编号: T-T14\n执行者: DEV-AI\n证据路径: data/02_交付物/代码/demo.py\n交付路径: data/02_交付物/代码/demo.py\n\n已完成实现。\n",
        encoding="utf-8",
    )
    rec = app_client.post(f"/api/handoff/recycle/{order['id']}", headers=headers).json()
    assert rec["status"] == "已回收"
    assert rec["ledger"]["version"] == "V1.0"
    assert app_client.get(f"/api/tasks/{task['id']}", headers=headers).json()["summary"]

    # 台账已登记
    versions = app_client.get("/api/versions", headers=headers).json()
    assert versions and versions[0]["item_name"] == "T-T14 交接任务"

    closed = app_client.post(f"/api/handoff/{order['id']}/close", headers=headers).json()
    assert closed["status"] == "已闭环"


def test_recycle_without_completion_file(app_client, headers):
    task = _task(app_client, headers)
    feed = app_client.post(f"/api/handoff/feed/{task['id']}", params={"receiver": "DEV-AI"},
                           headers=headers).json()
    order = app_client.get("/api/handoff", headers=headers).json()[0]
    r = app_client.post(f"/api/handoff/recycle/{order['id']}", headers=headers)
    assert r.status_code == 404 and "未在「完成/」目录找到" in r.json()["detail"]
    assert feed["status"] == "已投喂"


def test_recycle_not_found_and_illegal(app_client, headers):
    assert app_client.post("/api/handoff/recycle/nope", headers=headers).status_code == 404
    assert app_client.post("/api/handoff/nope/close", headers=headers).status_code == 404
    task = _task(app_client, headers)
    assert app_client.post(f"/api/handoff/feed/nope", headers=headers).status_code == 404


def test_sync_db_to_file_and_back(app_client, headers):
    task = _task(app_client, headers)
    feed = app_client.post(f"/api/handoff/feed/{task['id']}", params={"receiver": "DEV-AI"},
                           headers=headers).json()
    order = app_client.get("/api/handoff", headers=headers).json()[0]

    res = app_client.post("/api/handoff/sync", params={"direction": "to"}, headers=headers).json()
    assert res["count"] >= 1

    # 外部 AI 修改交接单 JSON：状态推进到「已闭环」应被识别为非法冲突
    from server.app.services.handoff_sync import ledger_path

    payload = json.loads(ledger_path().read_text(encoding="utf-8"))
    payload["orders"][0]["status"] = "已闭环"
    ledger_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    res = app_client.post("/api/handoff/sync", params={"direction": "from"}, headers=headers).json()
    assert res["created"] == 0 and res["conflicts"], res
    assert app_client.get("/api/handoff", headers=headers).json()[0]["status"] == "已投喂"

    # 合法的方向 ρ：文件推进到「已回收」应被接受
    payload["orders"][0]["status"] = "已回收"
    ledger_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    res = app_client.post("/api/handoff/sync", params={"direction": "from"}, headers=headers).json()
    assert res["updated"] == 1 and not res["conflicts"]
    assert app_client.get("/api/handoff", headers=headers).json()[0]["status"] == "已回收"
    assert len(order) > 0


def test_sync_missing_ledger_file(app_client, headers):
    from server.app.services.handoff_sync import ledger_path

    if ledger_path().exists():
        ledger_path().unlink()
    res = app_client.post("/api/handoff/sync", params={"direction": "from"}, headers=headers).json()
    assert res["created"] == 0


def test_broken_json_is_safely_reported(app_client, headers):
    from server.app.services.handoff_sync import ledger_path

    ledger_path().write_text("{ broken json", encoding="utf-8")
    res = app_client.post("/api/handoff/sync", params={"direction": "from"}, headers=headers).json()
    assert "error" in res and "解析失败" in res["error"]
