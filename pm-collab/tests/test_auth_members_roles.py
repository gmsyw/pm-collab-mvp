"""认证 / 成员名册 / 角色卡 的集成测试（T08/T09）。"""
from __future__ import annotations

ROLE_PAYLOAD = {
    "code": "ROLE-QA-TEST", "role_type": "AI角色", "duty": "集成与回归测试",
    "negative_list": "不复核自身产出", "permission_level": "L3",
    "data_boundary": "tests/ 只读源码", "reports_to": "PM", "downgrade_plan": "外部角色复核",
}


def test_login_ok_and_me(app_client):
    r = app_client.post("/api/auth/login", json={"username": "admin", "password": ""})
    assert r.status_code == 200 and r.json()["username"] == "admin"
    token = r.json()["access_token"]
    me = app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["member_type"] == "人类"


def test_login_bad_password(app_client):
    r = app_client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_unauthorized_requests_rejected(app_client):
    for path in ("/api/tasks", "/api/roles", "/api/members", "/api/handoff", "/api/checkpoints"):
        assert app_client.get(path).status_code == 401, path


def test_invalid_token_rejected(app_client):
    for token in ("", "not-a-jwt", "abc.def.ghi"):
        r = app_client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401 or r.status_code == 403


def test_role_crud_and_illegal_field(app_client, headers):
    r = app_client.post("/api/roles", json={**ROLE_PAYLOAD, "hacker_field": 1}, headers=headers)
    assert r.status_code == 422  # 非法字段被拒

    r = app_client.post("/api/roles", json={**ROLE_PAYLOAD, "permission_level": "L9"}, headers=headers)
    assert r.status_code == 422  # 非法权限等级被拒

    r = app_client.post("/api/roles", json=ROLE_PAYLOAD, headers=headers)
    assert r.status_code == 201
    role_id = r.json()["id"]

    r = app_client.post("/api/roles", json=ROLE_PAYLOAD, headers=headers)
    assert r.status_code == 409  # 编号重复

    r = app_client.put(f"/api/roles/{role_id}", json={**ROLE_PAYLOAD, "permission_level": "L2"}, headers=headers)
    assert r.status_code == 200 and r.json()["permission_level"] == "L2"

    r = app_client.get("/api/roles", params={"permission_level": "L2"}, headers=headers)
    assert len(r.json()) == 1

    assert app_client.put("/api/roles/not-exist", json=ROLE_PAYLOAD, headers=headers).status_code == 404
    assert app_client.delete(f"/api/roles/{role_id}", headers=headers).status_code == 200
    assert app_client.delete(f"/api/roles/{role_id}", headers=headers).status_code == 404


def test_member_crud_and_type_filter(app_client, headers):
    payload = {"code": "AI-NEW", "name": "新 AI 成员", "member_type": "AI", "reports_to": "H-001"}
    r = app_client.post("/api/members", json=payload, headers=headers)
    assert r.status_code == 201
    member_id = r.json()["id"]

    assert app_client.post("/api/members", json=payload, headers=headers).status_code == 409
    ai = app_client.get("/api/members", params={"member_type": "AI"}, headers=headers).json()
    human = app_client.get("/api/members", params={"member_type": "人类"}, headers=headers).json()
    assert len(ai) == 1 and len(human) == 1
    assert app_client.delete(f"/api/members/{member_id}", headers=headers).status_code == 200
    assert app_client.delete(f"/api/members/{member_id}", headers=headers).status_code == 404


def test_member_with_password_can_login(app_client, headers):
    payload = {"code": "H-002", "name": "测试成员", "member_type": "人类",
               "username": "tester", "password": "tester-pass"}
    assert app_client.post("/api/members", json=payload, headers=headers).status_code == 201
    r = app_client.post("/api/auth/login", json={"username": "tester", "password": "tester-pass"})
    assert r.status_code == 200
