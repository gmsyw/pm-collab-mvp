"""OSS-07 / UR-7：CLI 口令重置命令测试。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# scripts 包不在可安装范围内，测试时显式把 pm-collab 根目录加入 sys.path。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.reset_password import reset_admin_password  # noqa: E402


def test_reset_password_changes_login(app_client, db):
    # 旧口令（bootstrap 默认空串）可登录
    old = app_client.post("/api/auth/login", json={"username": "admin", "password": ""})
    assert old.status_code == 200
    old_token = old.json()["access_token"]

    # 让旧 token 的 iat 早于即将写入的 token_valid_from（确保整数秒错位）
    time.sleep(1.1)
    new_pwd = reset_admin_password(db)

    # 新口令可登录
    r = app_client.post("/api/auth/login", json={"username": "admin", "password": new_pwd})
    assert r.status_code == 200 and r.json()["username"] == "admin"

    # 旧口令（空串）已失效
    bad = app_client.post("/api/auth/login", json={"username": "admin", "password": ""})
    assert bad.status_code == 401

    # 重置前签发的旧 token 被吊销（token_valid_from 生效）
    me = app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert me.status_code == 401
