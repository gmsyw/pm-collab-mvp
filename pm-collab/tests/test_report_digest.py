"""每日摘要、度量、追加式日志不可改删测试（T06/T21/T22）。"""
from __future__ import annotations

import sqlite3

from server.app.config import settings


def test_metrics_calculation(app_client, headers, db):
    from datetime import datetime, timezone

    from server.app.models import TaskCard

    db.add(TaskCard(code="T-A", title="A", status="关闭", ai_executor="DEV-AI",
                    due_date="2099-01-01", summary="done", evidence=["e.md"]))
    db.add(TaskCard(code="T-B", title="B", status="阻塞", blocked_reason="等待", due_date="2020-01-01"))
    db.commit()

    m = app_client.get("/api/report/metrics", headers=headers).json()
    assert m["task_total"] == 2 and m["task_closed"] == 1
    assert m["blocked_count"] == 1
    assert m["overdue_count"] == 1  # T-B 已逾期且非终态
    assert 0 <= m["on_time_rate"] <= 100
    assert m["ai_adoption_rate"] == 100.0
    assert datetime.now(tz=timezone.utc) is not None


def test_digest_generated_pushed_and_archived(app_client, headers, data_dir):
    res = app_client.post("/api/report/digest", params={"push": True}, headers=headers).json()
    assert res["period"] and res["pushed_at"]
    assert "每日摘要" in res["summary_text"]
    files = app_client.get("/api/report/latest", headers=headers).json()["files"]
    assert any("-日报-" in f for f in files)


def test_latest_digest_empty(app_client, headers):
    res = app_client.get("/api/report/latest", headers=headers).json()
    assert res["record"] is None


def test_digest_file_written_to_library(app_client, headers, data_dir):
    app_client.post("/api/report/digest", params={"push": True}, headers=headers)
    # 日报现写入各项目独立目录：data/projects/<项目编号>/03_日志/日报周报
    today_files = []
    for pdir in (data_dir / "projects").iterdir():
        d = pdir / "03_日志" / "日报周报"
        if d.exists():
            today_files += sorted(d.glob("*-日报-*.md"))
    assert today_files
    assert "## 四指标" in today_files[-1].read_text(encoding="utf-8")


def test_append_log_immutable_at_db_layer(db, headers, app_client):
    """追加式日志：UPDATE/DELETE 在库层即被拒绝（触发器 + REVOKE 精神）。"""
    from server.app.audit import write_log

    log = write_log(db, actor="PM-AI", action="测试写日志", change="记录一条")
    db.commit()

    conn = sqlite3.connect(settings.database_url.replace("sqlite:///", ""))
    try:
        for sql in (
            f"UPDATE append_logs SET change='tampered' WHERE id='{log.id}'",
            f"DELETE FROM append_logs WHERE id='{log.id}'",
        ):
            try:
                conn.execute(sql)
                raise AssertionError(f"应被拒绝却成功：{sql}")
            except sqlite3.IntegrityError:
                pass
    finally:
        conn.close()


def test_append_log_api_returns_records(app_client, headers, db):
    from server.app.audit import write_log

    write_log(db, actor="QM", action="qa 动作", change="x", next_step="y")
    db.commit()
    logs = app_client.get("/api/report/logs", headers=headers).json()
    assert logs["immutable"] is True and logs["total"] >= 1
    assert logs["items"][0]["action"] == "qa 动作"


def test_heartbeat_public(app_client):
    assert app_client.get("/api/report/heartbeat").json()["ok"] is True
