"""回归：WBS 层级归属严格性 + 项目独立资料目录。

需求：项目→里程碑→工作包→任务→子任务逐级归属、不可混乱；每个项目拥有自己的目录。
"""
from __future__ import annotations

from server.app.config import settings


def _login(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": ""})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_project(client, headers, code, name):
    r = client.post("/api/projects", json={"code": code, "name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_cross_project_milestone_blocked(app_client, headers):
    """工作包不允许挂到其它项目的里程碑下。"""
    p1 = _create_project(app_client, headers, "PROJ-H1", "层级项目一")
    p2 = _create_project(app_client, headers, "PROJ-H2", "层级项目二")
    r = app_client.post(
        f"/api/wbs/milestones?project_id={p2}",
        json={"code": "M2", "name": "M2"}, headers=headers,
    )
    assert r.status_code == 201, r.text
    m2 = r.json()["id"]
    r = app_client.post(
        f"/api/wbs/workpackages?project_id={p1}",
        json={"code": "WPX", "name": "WPX", "milestone_id": m2}, headers=headers,
    )
    # 跨项目里程碑不属于当前项目 -> 拒绝（404/409）
    assert r.status_code in (404, 409), r.text


def test_task_workpackage_must_belong_to_specified_milestone(app_client, headers):
    """任务指定里程碑 MB，却挂到属于 MA 的工作包 -> 层级归属冲突 409。"""
    pid = _create_project(app_client, headers, "PROJ-H3", "层级项目三")
    r = app_client.post(f"/api/wbs/milestones?project_id={pid}", json={"code": "MA", "name": "MA"}, headers=headers)
    ma = r.json()["id"]
    r = app_client.post(f"/api/wbs/milestones?project_id={pid}", json={"code": "MB", "name": "MB"}, headers=headers)
    mb = r.json()["id"]
    r = app_client.post(
        f"/api/wbs/workpackages?project_id={pid}",
        json={"code": "WPA", "name": "WPA", "milestone_id": ma}, headers=headers,
    )
    wpa = r.json()["id"]

    r = app_client.post(
        f"/api/tasks?project_id={pid}",
        json={"code": "T-H", "title": "层级任务", "milestone_id": mb, "work_package_id": wpa},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert "层级归属冲突" in r.text


def test_project_has_own_directory(app_client, headers):
    """新建项目应自动生成独立目录（五库 + 交接区）。"""
    code = "PROJ-DIR"
    _create_project(app_client, headers, code, "目录项目")
    root = settings.data_dir / "projects" / code
    assert root.exists(), f"项目目录未创建: {root}"
    assert (root / "01_项目库").exists()
    assert (root / "03_日志" / "日报周报").exists()
    assert (root / "交接区" / "派单").exists()
    assert (root / "交接区" / "交接单.json").exists()
