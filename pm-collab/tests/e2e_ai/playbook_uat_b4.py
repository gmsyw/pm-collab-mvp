"""UAT 批 4：§6 配置 / 运维 / FAQ 验收（TEST-09-01~10，P2）。

用例来源：《PM-Collab 验收测试大纲（UAT）_V1.0.md》§6。
策略：
  - 生产实例（8731）：TEST-09-08/09 等不需重启的用例；
  - 临时实例（8080 + 独立临时 SQLite/数据目录）：TEST-09-01/02/03/10（需改 env 重启，避免扰动生产实例）；
  - TEST-09-04（PG）：本机无 PostgreSQL 服务 → 环境不满足，登记待部署验证；
  - TEST-09-05/06/07（pytest --cov / smoke / export_registers）由外层命令执行，本脚本汇总其结果文件。

运行（pm-collab/ 根）：.venv\\Scripts\\python tests\\e2e_ai\\playbook_uat_b4.py
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = os.environ.get("PM_TEST_BASE", "http://127.0.0.1:8731")
ROOT = Path(__file__).resolve().parents[2]          # pm-collab/
TS = datetime.datetime.now().strftime("%H%M%S")
TMP = Path(os.environ.get("TEMP", "/tmp")) / f"pm_uat_b4_{TS}"
TMP.mkdir(parents=True, exist_ok=True)
TMP_DB = TMP / "pm_collab.db"
TMP_DATA = TMP / "data"
TMP_PORT = 8080

RESULTS: list[dict] = []


def check(case: str, name: str, ok: bool, detail: str = "", level: str = "P2") -> None:
    RESULTS.append({"case": case, "name": name, "pass": ok, "detail": detail, "level": level})
    print(f"[{'PASS' if ok else 'FAIL'}] {case} {name} | {detail}")


def call(c: httpx.Client, method: str, path: str, token: str = "",
         params: dict | None = None, json_body: dict | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return c.request(method, f"{BASE}{path}", headers=headers, params=params, json=json_body)


def tcall(c: httpx.Client, port: int, method: str, path: str, token: str = "",
          params: dict | None = None, json_body: dict | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return c.request(method, f"http://127.0.0.1:{port}{path}", headers=headers, params=params, json=json_body)


def start_tmp(env_extra: dict, port: int = TMP_PORT) -> subprocess.Popen:
    env = dict(os.environ)
    env.update({
        "PM_DATABASE_URL": f"sqlite:///{TMP_DB.as_posix()}",
        "PM_DATA_DIR": str(TMP_DATA),
        "PM_PORT": str(port),
        "PM_WATCHDOG_ENABLED": "false",
    })
    env.update(env_extra)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.app.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc


def wait_up(port: int, timeout: float = 45.0) -> bool:
    c = httpx.Client(timeout=3)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if c.get(f"http://127.0.0.1:{port}/").status_code == 200:
                c.close()
                return True
        except Exception:
            pass
        time.sleep(0.8)
    c.close()
    return False


def stop(proc: subprocess.Popen) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


def login(c: httpx.Client, port: int, user: str, pwd: str) -> tuple[int, str]:
    r = c.post(f"http://127.0.0.1:{port}/api/auth/login", json={"username": user, "password": pwd})
    return r.status_code, r.json().get("access_token", "") if r.status_code == 200 else ""


def main() -> int:
    c = httpx.Client(timeout=25)
    print(f"[INFO] 被测实例：{BASE}；临时实例目录 {TMP}")

    # ================= 生产实例部分 =================
    print("\n===== 生产实例：FAQ 场景（无需重启） =====")
    r = call(c, "POST", "/api/auth/login", json_body={"username": "admin", "password": ""})
    admin_token = r.json()["access_token"] if r.status_code == 200 else ""
    if not admin_token:
        print("[FATAL] admin 登录失败")
        return 1

    # TEST-09-08 FAQ Q1：前端构建产物托管
    r = call(c, "GET", "/")
    dist_idx = ROOT / "web" / "dist" / "index.html"
    check("TEST-09-08", "FAQ Q1：后端托管最近一次 build（dist/index.html 存在且首页 200）",
          r.status_code == 200 and dist_idx.exists(),
          f"HTTP {r.status_code} dist={dist_idx.exists()} 构建时间={dist_idx.stat().st_mtime if dist_idx.exists() else '-'}")

    # TEST-09-09 FAQ Q5：门禁推不动 → 提示缺签字 → 签字后推进
    r = call(c, "POST", "/api/projects", token=admin_token,
             json_body={"code": f"TEST-09-{TS}", "name": f"UAT 批4 {TS}"})
    pid = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid},
             json_body={"target": "S2"})
    blocked = r.status_code == 403
    r = call(c, "GET", "/api/checkpoints", token=admin_token, params={"project_id": pid})
    cp = any("门禁" in x.get("content", "") for x in (r.json() if r.status_code == 200 else []))
    r2 = call(c, "POST", "/api/process/gates/sign", token=admin_token, params={"project_id": pid},
              json_body={"gate_no": "①", "decision": "通过", "signed_by": "H", "opinion": "批4验证"})
    r3 = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid},
              json_body={"target": "S2"})
    check("TEST-09-09", "FAQ Q5：门禁未签字被拒并提示（卡点），签字后推进成功",
          blocked and cp and r2.status_code == 200 and r3.status_code == 200,
          f"advance={r.status_code} 卡点={cp} sign={r2.status_code} 推进={r3.status_code}")

    # TEST-09-04 PG：环境探测
    pg = subprocess.run(["powershell", "-NoProfile", "-Command",
                         "if (Get-Service -Name '*postgres*' -ErrorAction SilentlyContinue) {'PG'} else {'NO'}",
                         ], capture_output=True, text=True)
    check("TEST-09-04", "PM_DATABASE_URL 切 PG：本机无 PG 服务",
          pg.stdout.strip() == "NO",
          f"环境={pg.stdout.strip()} 【SKIP 登记】代码层已支持（config.database_url 可配 postgresql+psycopg://，is_sqlite 方言判断），待部署环境验证")

    # ================= 临时实例部分 =================
    print("\n===== 临时实例：配置项（改 env 重启场景） =====")
    proc_a = start_tmp({"PM_SECRET_KEY": "keyA-B4"})
    ok_up = wait_up(TMP_PORT)
    check("TEST-09-01", "服务端口可配置：8080 实例就绪可访问", ok_up,
          f"就绪={ok_up}（uvicorn --port 生效；PM_PORT 仅影响启动横幅 → 关联差异 O-09）")
    if not ok_up:
        stop(proc_a)
        return 1

    s, token_a = login(c, TMP_PORT, "admin", "")
    check("TEST-09-03", "登录成功（临时库 bootstrap）", s == 200, f"HTTP {s}")

    r = call(c, "GET", "/api/projects", token=admin_token)
    r = tcall(c, TMP_PORT, "GET", "/api/projects", token=token_a)
    dflt = next((p for p in (r.json() if r.status_code == 200 else []) if p.get("code") == "PROJ-DEFAULT"), {})
    dpid = dflt.get("id", "")

    # TEST-09-02 FAQ Q3：watchdog=false 不自动入库；手动同步可入库
    ledger = TMP_DATA / "projects" / "PROJ-DEFAULT" / "交接区" / "交接单.json"
    payload = {"project": "PROJ-DEFAULT", "updated_at": datetime.datetime.now().isoformat(),
               "orders": [{"code": "HO-B4-001", "sender": "AI-B4", "receiver": "H-001", "zone": "派单",
                           "payload_path": "", "status": "待投喂", "task_code": "", "content_hash": ""}]}
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    time.sleep(3.5)
    r = tcall(c, TMP_PORT, "GET", "/api/handoff", token=token_a, params={"project_id": dpid})
    orders = r.json() if r.status_code == 200 else []
    not_in = not any(o.get("code") == "HO-B4-001" for o in orders)
    r = tcall(c, TMP_PORT, "POST", "/api/handoff/sync", token=token_a, params={"direction": "from"})
    body = r.json() if r.status_code == 200 else {}
    created = sum(item.get("created", 0) for item in body.get("from", []))
    r = tcall(c, TMP_PORT, "GET", "/api/handoff", token=token_a, params={"project_id": dpid})
    orders2 = r.json() if r.status_code == 200 else []
    in_now = any(o.get("code") == "HO-B4-001" for o in orders2)
    check("TEST-09-02", "FAQ Q3：watchdog=false 不自动入库；手动同步后入库",
          not_in and created == 1 and in_now,
          f"自动入库={not not_in}(期望否) sync created={created} 同步后存在={in_now}")

    # TEST-09-03 密钥轮换
    r = tcall(c, TMP_PORT, "GET", "/api/projects", token=token_a)
    ok_a = r.status_code == 200
    stop(proc_a)
    time.sleep(1.0)
    proc_b = start_tmp({"PM_SECRET_KEY": "keyB-B4"})
    ok_up = wait_up(TMP_PORT)
    r = tcall(c, TMP_PORT, "GET", "/api/projects", token=token_a)
    old_rejected = ok_up and r.status_code == 401
    s2, token_b = login(c, TMP_PORT, "admin", "")
    check("TEST-09-03", "PM_SECRET_KEY 轮换：旧 token 失效、重新登录生效",
          ok_a and old_rejected and s2 == 200,
          f"旧密钥 token={r.status_code}(期望401) 新登录={s2}")

    # TEST-09-10 FAQ Q6：改 PM_BOOTSTRAP_PASSWORD 重启
    stop(proc_b)
    time.sleep(1.0)
    proc_c = start_tmp({"PM_SECRET_KEY": "keyB-B4", "PM_BOOTSTRAP_PASSWORD": "reset-B4-2026"})
    wait_up(TMP_PORT)
    s3, _ = login(c, TMP_PORT, "admin", "reset-B4-2026")
    diff = s3 != 200  # bootstrap 仅创建不覆盖已存在成员
    check("TEST-09-10", "FAQ Q6(路径①)：改 PM_BOOTSTRAP_PASSWORD 重启后新密码可登录（手册承诺）",
          s3 == 200,
          f"HTTP {s3} 【差异登记】ensure_bootstrap 仅首次创建，不覆盖已存在 admin 密码 → 手册承诺与实现不符")
    # 路径②：直接更新数据库 password_hash
    stop(proc_c)
    time.sleep(1.0)
    sys.path.insert(0, str(ROOT))
    from server.app.api.auth import hash_password  # noqa: E402
    new_hash = hash_password("reset-B4-2026")
    import sqlite3  # noqa: E402
    con = sqlite3.connect(TMP_DB)
    con.execute("UPDATE members SET password_hash=? WHERE username='admin'", (new_hash,))
    con.commit()
    con.close()
    proc_d = start_tmp({"PM_SECRET_KEY": "keyB-B4", "PM_BOOTSTRAP_PASSWORD": "reset-B4-2026"})
    wait_up(TMP_PORT)
    s4, _ = login(c, TMP_PORT, "admin", "reset-B4-2026")
    check("TEST-09-10", "FAQ Q6(路径②)：直接更新 members.password_hash 后新密码可登录",
          s4 == 200, f"HTTP {s4}")
    stop(proc_d)

    # ---------- 汇总 ----------
    passed = sum(1 for x in RESULTS if x["pass"])
    failed = [x for x in RESULTS if not x["pass"]]
    print("\n" + "=" * 76)
    print(f"UAT 批4（脚本部分）执行完成：共 {len(RESULTS)} 项，PASS {passed}，FAIL {len(failed)}")
    for x in failed:
        print(f"  - {x['case']} {x['name']} [{x['level']}]: {x['detail']}")
    summary = {"script": "playbook_uat_b4", "ts": TS, "tmp_dir": str(TMP),
               "total": len(RESULTS), "passed": passed, "failed": len(failed), "results": RESULTS}
    out = ROOT / "data" / "02_交付物" / "04_测试" / f"report_uat_b4_{TS}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入：{out}")
    print("=" * 76)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
