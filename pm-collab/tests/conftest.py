"""pytest 公共夹具：隔离的临时数据库与文件库。

说明：环境变量须在任何 server 模块导入前设置，故置于本文件顶部。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="pmcollab-test-"))
os.environ["PM_DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["PM_DATA_DIR"] = str(_TMP / "data")
os.environ["PM_HANDOFF_DIR"] = str(_TMP / "data" / "交接区")
os.environ["PM_WATCHDOG_ENABLED"] = "false"
os.environ["PM_SCHEDULER_ENABLED"] = "false"
os.environ["PM_SECRET_KEY"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from server.app.db import Base, SessionLocal, engine  # noqa: E402
from server.app.main import create_app  # noqa: E402
from server.app.models import Member, TaskCard  # noqa: E402
from server.app.security import hash_password  # noqa: E402
from server.app.services.db_bootstrap import init_db  # noqa: E402
from server.app.services.five_libs import ensure_libraries  # noqa: E402

ADMIN = ("admin", "REMOVED-FOR-OPENSOURCE")


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_db():
    init_db()
    yield


@pytest.fixture(autouse=True)
def _clean_zone_files():
    """每个用例前清空交接区文件，避免用例间互相污染（文件库为会话级临时目录）。"""
    from server.app.services.five_libs import HANDOFF_ZONES, ensure_libraries, zone_path

    ensure_libraries()
    for zone in HANDOFF_ZONES:
        for f in zone_path(zone).iterdir():
            if f.is_file():
                f.unlink()
    yield


@pytest.fixture()
def db() -> Session:
    """每用例清库，保证测试独立性（多线程/licloud 无关）。"""
    Base.metadata.drop_all(engine)
    init_db()
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def app_client(db):
    app = create_app(start_services=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def headers(app_client) -> dict[str, str]:
    r = app_client.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def ai_headers(db, app_client) -> dict[str, str]:
    """AI 成员令牌：用于验证「AI 不可代签门禁」。"""
    ai = Member(code="AI-TEST", name="测试AI", member_type="AI", status="在岗",
                username="ai_bot", password_hash=hash_password("ai-pass"))
    db.add(ai)
    db.commit()
    r = app_client.post("/api/auth/login", json={"username": "ai_bot", "password": "ai-pass"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def task_fixture(db) -> TaskCard:
    task = TaskCard(code="T-T01", title="测试用例任务", priority="P0",
                    deliverables="data/x.py", acceptance="接口通过")
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@pytest.fixture()
def data_dir() -> Path:
    ensure_libraries()
    from server.app.config import settings

    return settings.data_dir
