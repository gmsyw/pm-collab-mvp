"""项目实体：新建/列表/去重 + 任务与流程按项目隔离（需求书 §4.1）。"""
from __future__ import annotations


def _create_project(app_client, headers, code):
    r = app_client.post("/api/projects", json={"code": code, "name": code}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_project_and_list(app_client, headers):
    pid = _create_project(app_client, headers, "PROJ-A")
    lst = app_client.get("/api/projects", headers=headers).json()
    assert any(p["id"] == pid for p in lst)


def test_create_project_duplicate_rejected(app_client, headers):
    _create_project(app_client, headers, "PROJ-DUP")
    r = app_client.post("/api/projects", json={"code": "PROJ-DUP", "name": "Y"}, headers=headers)
    assert r.status_code == 409


def test_tasks_scoped_by_project(app_client, headers):
    pid_b = _create_project(app_client, headers, "PROJ-B")
    pid_c = _create_project(app_client, headers, "PROJ-C")

    assert app_client.post(
        "/api/tasks", json={"code": "TX1", "title": "B任务"},
        params={"project_id": pid_b}, headers=headers,
    ).status_code == 201
    assert app_client.post(
        "/api/tasks", json={"code": "TX2", "title": "C任务"},
        params={"project_id": pid_c}, headers=headers,
    ).status_code == 201

    in_b = app_client.get("/api/tasks", params={"project_id": pid_b}, headers=headers).json()
    in_c = app_client.get("/api/tasks", params={"project_id": pid_c}, headers=headers).json()

    assert any(t["code"] == "TX1" for t in in_b) and not any(t["code"] == "TX2" for t in in_b)
    assert any(t["code"] == "TX2" for t in in_c) and not any(t["code"] == "TX1" for t in in_c)


def test_new_project_has_own_process_and_gates(app_client, headers):
    pid = _create_project(app_client, headers, "PROJ-C2")
    inst = app_client.get("/api/process/instance", params={"project_id": pid}, headers=headers).json()
    assert inst["stage"] == "S1"
    gates = app_client.get("/api/process/gates", params={"project_id": pid}, headers=headers).json()
    assert len(gates) == 4
    assert {g["gate_no"] for g in gates} == {"①", "②", "③", "④"}
