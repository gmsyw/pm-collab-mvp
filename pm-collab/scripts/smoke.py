"""端到端冒烟自测：一次跑通 MVP 主链路（派单→回执→完成→回收→台账 + 门禁 + 摘要）。

用法：python scripts/smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from server.app.main import create_app  # noqa: E402
from server.app.services.db_bootstrap import init_db  # noqa: E402

OK, FAIL = "[PASS]", "[FAIL]"
results: list[tuple[bool, str, str]] = []
sys.stdout.reconfigure(encoding="utf-8")


def check(cond: bool, name: str, detail: str = "") -> None:
    results.append((cond, name, detail))
    print(f"{OK if cond else FAIL} {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    init_db()
    app = create_app(start_services=False)
    c = TestClient(app)

    check(c.get("/api/report/heartbeat").json()["ok"], "服务心跳", "/api/report/heartbeat")
    check(c.get("/api/tasks").status_code == 401, "未授权请求被拒", "401")

    r = c.post("/api/auth/login", json={"username": "admin", "password": "REMOVED-FOR-OPENSOURCE"})
    check(r.status_code == 200, "登录签发 JWT", r.json().get("username", ""))
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    libs = c.get("/api/libs/tree", headers=h).json()["libraries"]
    check(len(libs) >= 6, "五库+交接区托管", f"{len(libs)} 个顶层库")
    zones = c.get("/api/handoff/zones", headers=h).json()["files"]
    check(len(zones) == 6, "交接区 6 目录就绪", ",".join(zones))

    # 角色卡校验
    check(c.post("/api/roles", json={"code": "R-X", "duty": "x", "bogus": 1}, headers=h).status_code == 422,
          "角色卡非法字段被拒", "bogus")
    check(c.post("/api/roles", json={"code": "R-X", "duty": "x", "permission_level": "L9"}, headers=h).status_code == 422,
          "角色卡非法权限等级被拒", "L9")

    # 任务卡 + 状态机
    t = c.post("/api/tasks", json={"code": "T-SMOKE", "title": "冒烟任务", "ai_executor": "DEV-AI",
                                   "due_date": "2026-01-01"}, headers=h).json()
    tid = t["id"]
    check(c.post(f"/api/tasks/{tid}/transition", json={"target": "关闭"}, headers=h).status_code == 409,
          "非法状态迁移被拒", "待办→关闭")
    check(c.post(f"/api/tasks/{tid}/transition", json={"target": "进行中"}, headers=h).status_code == 200,
          "待办→进行中", "OK")
    check(c.post(f"/api/tasks/{tid}/transition", json={"target": "待评审"}, headers=h).status_code == 422,
          "无证据不得置为待评审", "422")
    c.post(f"/api/tasks/{tid}/evidence", json={"paths": ["data/02_交付物/代码/mock.py"],
                                              "summary": "冒烟完成"}, headers=h)
    check(c.post(f"/api/tasks/{tid}/transition", json={"target": "待评审"}, headers=h).status_code == 200,
          "补证据后进入待评审", "OK")

    # 交接总线：投喂 → 写回完成 → 回收 → 台账
    feed = c.post(f"/api/handoff/feed/{tid}", params={"receiver": "DEV-AI"}, headers=h).json()
    check(feed["status"] == "已投喂", "投喂助手生成派单文件", Path(feed["file"]).name)
    order_id = c.get("/api/handoff", headers=h).json()[0]["id"]

    done_file = Path(feed["file"]).parent.parent / "完成" / "T-SMOKE_完成_冒烟_V1.md"
    done_file.write_text(
        "任务编号: T-SMOKE\n执行者: DEV-AI\n证据路径: data/02_交付物/代码/mock.py\n交付路径: data/02_交付物/代码/mock.py\n\n冒烟完成摘要。\n",
        encoding="utf-8",
    )
    rec = c.post(f"/api/handoff/recycle/{order_id}", headers=h).json()
    check(rec["status"] == "已回收", "回收助手回收闭环", rec["file"])
    check(rec.get("ledger", {}).get("version") == "V1.0", "回收后登记版本台账", str(rec.get("ledger")))
    check(rec.get("task_status") == "待评审", "任务回填为待评审", str(rec.get("task_status")))
    check(c.post(f"/api/handoff/{order_id}/close", headers=h).json()["status"] == "已闭环", "交接单闭环", "OK")

    # 交接单状态机非法迁移（已闭环→已投喂）
    check(c.post(f"/api/handoff/{order_id}/transition", json={"target": "已投喂"}, headers=h).status_code == 409,
          "交接单非法迁移被拒", "已闭环→已投喂")

    # 门禁与阶段推进
    adv = c.post("/api/process/advance", json={"target": "S2"}, headers=h)
    check(adv.status_code == 403, "无门禁签字不放行", adv.json().get("detail", "")[:40])
    check(c.post("/api/process/gates/sign", json={"gate_no": "①", "decision": "通过",
                                                  "signed_by": "H"}, headers=h).status_code == 200,
          "人类签署门禁①", "OK")
    check(c.post("/api/process/advance", json={"target": "S2"}, headers=h).status_code == 200,
          "签字后阶段放行 S1→S2", "OK")

    # 追加日志不可改删
    import sqlite3

    from server.app.config import settings

    if settings.is_sqlite:
        conn = sqlite3.connect(str(settings.database_url.replace("sqlite:///", "")))
        try:
            conn.execute("UPDATE append_logs SET change='tampered'")
            tamper = "未被拦截"
        except sqlite3.IntegrityError:
            tamper = "已拦截"
        finally:
            conn.close()
        check(tamper == "已拦截", "追加式日志 UPDATE 被库层拒绝", "SQLite 触发器")

    # 每日摘要
    dig = c.post("/api/report/digest", params={"push": True}, headers=h).json()
    check(dig["period"] and dig["pushed_at"], "每日摘要生成并推送", dig["period"])

    passed = sum(1 for ok, _, _ in results if ok)
    print(f"\n通过 {passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
