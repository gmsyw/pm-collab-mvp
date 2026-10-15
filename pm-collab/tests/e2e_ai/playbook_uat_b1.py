"""UAT 批 1：US-01 部署与启动 + US-02 身份与项目（对照使用手册 MVP v0.1.0）。

用例来源：《PM-Collab 验收测试大纲（UAT）_V1.0.md》批 1（TEST-01-xx / TEST-02-xx）。
判定：期望结果引自手册承诺；DEF-05（编辑项目状态字段）按大纲登记为 P0 验收失败项。
运行（pm-collab/ 根）：.venv\\Scripts\\python tests\\e2e_ai\\playbook_uat_b1.py
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

import httpx

BASE = os.environ.get("PM_TEST_BASE", "http://127.0.0.1:8731")
EXTERNAL = os.environ.get("PM_TEST_EXTERNAL") == "1"
INSECURE = os.environ.get("PM_TEST_INSECURE") == "1"
TS = datetime.datetime.now().strftime("%H%M%S")
PROJ_A = f"TEST-02-{TS}"
PROJ_B = f"TEST-02B-{TS}"

RESULTS: list[dict] = []


def check(case: str, name: str, ok: bool, detail: str = "", level: str = "P0") -> None:
    RESULTS.append({"case": case, "name": name, "pass": ok, "detail": detail, "level": level})
    print(f"[{'PASS' if ok else 'FAIL'}] {case} {name} | {detail}")


def call(c: httpx.Client, method: str, path: str, token: str = "",
         params: dict | None = None, json_body: dict | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return c.request(method, f"{BASE}{path}", headers=headers, params=params, json=json_body)


def main() -> int:
    c = httpx.Client(timeout=25, verify=not INSECURE)
    print(f"[INFO] 被测实例：{BASE} EXTERNAL={EXTERNAL}")
    root = Path(__file__).resolve().parents[2]

    # ================= US-01 部署与启动（基于运行实例核验） =================
    print("\n===== US-01 部署与启动 =====")

    # TEST-01-01 初始化状态（seed 完成证据：库文件 + 默认项目 + 流程门禁）
    db_file = root / "data" / "pm_collab.db"
    ok = db_file.exists() and db_file.stat().st_size > 0
    check("TEST-01-01", "seed 初始化：数据库文件存在", ok, f"大小={db_file.stat().st_size if ok else 0}B", "P0")
    r = call(c, "POST", "/api/auth/login", json_body={"username": "admin", "password": ""})
    admin_token = r.json()["access_token"] if r.status_code == 200 else ""
    r = call(c, "GET", "/api/projects", token=admin_token)
    projs = r.json() if r.status_code == 200 else []
    default_ok = any(p.get("code") == "PROJ-DEFAULT" for p in projs)
    check("TEST-01-01", "seed 初始化：默认项目存在", r.status_code == 200 and default_ok,
          f"HTTP {r.status_code} 项目总数={len(projs)} 含PROJ-DEFAULT={default_ok}", "P0")

    # TEST-01-02 启动日志核验（对照手册 §2.2；server.out.log 为 GBK 编码）
    out_log = ""
    log_path = root / "server.out.log"
    if log_path.exists():
        out_log = log_path.read_bytes().decode("gbk", errors="ignore")
    ok1 = "[startup]" in out_log and "独立资料目录" in out_log
    ok2 = "[scheduler]" in out_log and "每日摘要" in out_log
    ok3 = "[watchdog]" in out_log
    check("TEST-01-02", "启动日志：[startup] 独立资料目录 + [scheduler] 摘要任务", ok1 and ok2,
          f"startup={ok1} scheduler={ok2}", "P0")
    check("TEST-01-02", "启动日志：[watchdog] 交接区同步（手册 §2.2 承诺）", ok3,
          f"[watchdog] 行出现={ok3} 【观察项 O-10】手册承诺启动横幅，当前代码仅异常时打印", "P2")

    # TEST-01-03 首页可达 + 标题
    r = call(c, "GET", "/")
    title_ok = "PM-Collab" in r.text and "<title>" in r.text
    check("TEST-01-03", "首页可达（非空白）", r.status_code == 200 and title_ok,
          f"HTTP {r.status_code} 含<title>={title_ok}（FAQ Q1 反向）", "P0")

    # TEST-01-04 /docs 交互式 API 文档
    r = call(c, "GET", "/docs")
    docs_ok = "swagger" in r.text.lower() or "openapi" in r.text.lower()
    check("TEST-01-04", "/docs 交互式 API 文档可达", r.status_code == 200 and docs_ok,
          f"HTTP {r.status_code} Swagger特征={docs_ok}", "P2")

    # TEST-01-05 未登录访问业务接口被拦截
    r = call(c, "GET", "/api/tasks")
    check("TEST-01-05", "未登录访问业务接口被拦截", r.status_code == 401, f"HTTP {r.status_code}", "P0")

    # 启动横幅观察项：banner 端口 vs 实际监听
    banner_port = "[startup] PM-Collab 人机共用项目管理软件 v0.1.0 @ 127.0.0.1:8000" in out_log
    check("TEST-01-02", "启动横幅端口与手册一致（8000）", banner_port,
          f"banner显示8000={banner_port} 实际被测={BASE} 【观察项 O-09】banner 与实际监听端口可能不一致", "P2")

    # ================= US-02 身份与项目 =================
    print("\n===== US-02 身份与项目 =====")

    # TEST-02-01 正确账号登录
    ok = admin_token != ""
    check("TEST-02-01", "正确账号登录", ok, f"HTTP {r.status_code if not ok else 200}", "P0")

    # TEST-02-02 错误密码 / 缺字段
    r = call(c, "POST", "/api/auth/login", json_body={"username": "admin", "password": "wrong"})
    check("TEST-02-02", "错误密码登录被拒", r.status_code == 401, f"HTTP {r.status_code}", "P0")
    r = call(c, "POST", "/api/auth/login", json_body={"password": ""})
    check("TEST-02-02", "登录缺字段被拒", r.status_code == 422, f"HTTP {r.status_code}", "P0")

    # TEST-02-03 新建项目 + 独立资料目录
    r = call(c, "POST", "/api/projects", token=admin_token,
             json_body={"code": PROJ_A, "name": f"UAT 批1 项目A {TS}",
                        "description": "TEST-02 验收项目", "owner": "Dr Ming"})
    pid_a = r.json().get("id", "") if r.status_code == 201 else ""
    ok = r.status_code == 201 and bool(pid_a)
    check("TEST-02-03", "新建项目成功", ok, f"HTTP {r.status_code}", "P0")
    if ok and not EXTERNAL:
        proot = root / "data" / "projects" / PROJ_A
        libs_ok = all((proot / lib).exists() for lib in ("01_项目库", "02_交付物", "03_日志", "04_模板", "05_版本库"))
        zones_ok = (proot / "交接区" / "派单").exists() and (proot / "交接区" / "交接单.json").exists()
        check("TEST-02-03", "独立资料目录（五库+交接区+交接单）", proot.exists() and libs_ok and zones_ok,
              f"五库={libs_ok} 交接区={zones_ok} 路径={proot}", "P0")
    else:
        check("TEST-02-03", "独立资料目录（外部实例跳过）", True, "SKIP 外部实例无本地文件系统", "P0")

    # TEST-02-04a 编辑项目：名称/描述/负责人可改、编号不可改
    r = call(c, "PUT", f"/api/projects/{pid_a}", token=admin_token,
             json_body={"code": "HACK-CHG", "name": f"TEST-02-{TS}-改名", "description": "验收后描述",
                        "owner": "Dr Ming"})
    body = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and body.get("code") == PROJ_A and body.get("name", "").endswith("改名")
    check("TEST-02-04", "编辑项目：名称/描述生效，编号不可改", ok,
          f"HTTP {r.status_code} code={body.get('code')} name={body.get('name')}", "P0")

    # TEST-02-04b 编辑项目状态（手册 §4.1 承诺）→ DEF-05 修复回归（当前代码已用 ProjectUpdateIn）
    r = call(c, "PUT", f"/api/projects/{pid_a}", token=admin_token,
             json_body={"code": PROJ_A, "name": "x", "status": "挂起"})
    body = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and body.get("status") == "挂起" and body.get("code") == PROJ_A
    check("TEST-02-04", "编辑项目状态（手册承诺可改）", ok,
          f"HTTP {r.status_code} status={body.get('status')} 【DEF-05 修复回归：原 422 已转 200】", "P0")

    # TEST-02-05 建第二项目 + 项目隔离
    r = call(c, "POST", "/api/projects", token=admin_token,
             json_body={"code": PROJ_B, "name": f"UAT 批1 项目B {TS}", "owner": "Dr Ming"})
    pid_b = r.json().get("id", "") if r.status_code == 201 else ""
    ok = r.status_code == 201 and bool(pid_b)
    check("TEST-02-05", "新建第二个项目", ok, f"HTTP {r.status_code}", "P0")
    # A 项目建一个私有成员，B 项目视角不可见（隔离）
    if ok:
        r = call(c, "POST", "/api/members", token=admin_token, params={"project_id": pid_a},
                 json_body={"code": f"UATA-M-{TS}", "name": "A项目成员", "member_type": "H", "status": "在岗"})
        r = call(c, "GET", "/api/members", token=admin_token, params={"project_id": pid_b})
        b_codes = [m.get("code", "") for m in (r.json() if r.status_code == 200 else [])]
        isolated = all(not x.startswith("UATA-M-") for x in b_codes)
        check("TEST-02-05", "项目隔离：A 成员在 B 项目不可见", r.status_code == 200 and isolated,
              f"HTTP {r.status_code} B 项目成员含A专属={not isolated}", "P0")

    # TEST-02-06 编号重复 / 缺必填
    r = call(c, "POST", "/api/projects", token=admin_token, json_body={"code": PROJ_A, "name": "dup"})
    check("TEST-02-06", "项目编号重复被拒", r.status_code == 409, f"HTTP {r.status_code}", "P1")
    r = call(c, "POST", "/api/projects", token=admin_token, json_body={"code": f"TEST-X-{TS}"})
    check("TEST-02-06", "建项目缺必填 name 被拒", r.status_code == 422, f"HTTP {r.status_code}", "P1")

    # TEST-02-07 缺陷修复回归：DEF-04（文档不带 path 默认落五库）+ DEF-07（doc_no 全局唯一）
    r = call(c, "POST", "/api/docs", token=admin_token, params={"project_id": pid_a},
             json_body={"doc_no": f"R-{TS}", "name": "批1回归", "version": "V1.0.0", "library": "01_项目库"})
    dbody = r.json() if r.status_code == 201 else {}
    dpath = dbody.get("path", "")
    ok = r.status_code == 201 and (EXTERNAL or str(PROJ_A) in dpath) and "-V1.0.0.md" in dpath
    check("TEST-02-07", "DEF-04 修复回归：文档默认落项目五库（合规命名）", ok,
          f"HTTP {r.status_code} path={dpath or '空'}", "P0")
    # DEF-07 复现：A 项目用已存在的 doc_no（B 项目新项目也撞全局唯一 R-<TS>）
    r = call(c, "POST", "/api/docs", token=admin_token, params={"project_id": pid_b},
             json_body={"doc_no": f"R-{TS}", "name": "批1回归B", "version": "V1.0.0", "library": "01_项目库"})
    check("TEST-02-07", "DEF-07 登记：doc_no 应项目内唯一但实为全局唯一", r.status_code == 201,
          f"HTTP {r.status_code} 【缺陷 DEF-07】doc_entries.doc_no 全局唯一约束，B 项目沿用 A 项目编号被拒；且未捕获 IntegrityError（复现轮返回 500）", "P0")

    # ================= 汇总 =================
    passed = sum(1 for x in RESULTS if x["pass"])
    failed = [x for x in RESULTS if not x["pass"]]
    print("\n" + "=" * 76)
    print(f"UAT 批1 执行完成：共 {len(RESULTS)} 项，PASS {passed}，FAIL {len(failed)}（P0 失败 {sum(1 for x in failed if x['level']=='P0')}）")
    for x in failed:
        print(f"  - {x['case']} {x['name']} [{x['level']}]: {x['detail']}")
    summary = {"script": "playbook_uat_b1", "ts": TS, "project_a": PROJ_A, "project_b": PROJ_B,
               "total": len(RESULTS), "passed": passed, "failed": len(failed), "results": RESULTS}
    out = root / "data" / "02_交付物" / "04_测试" / f"report_uat_b1_{TS}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入：{out}")
    print("=" * 76)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
