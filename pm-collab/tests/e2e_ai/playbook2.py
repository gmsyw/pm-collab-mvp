"""剧本2 端到端执行脚本：子任务独立推进（子任务状态机 + 证据）。

运行：.venv\\Scripts\\python tests\\e2e_ai\\playbook2.py
对应用例：PMT-AI2-*（子任务推进专项）
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8731"
TS = datetime.datetime.now().strftime("%H%M%S")
PROJ_CODE = f"T-AI2-{TS}"
RESULTS: list[dict] = []


def check(case_id: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"case": case_id, "name": name, "pass": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {case_id} {name}" + (f" | {detail}" if detail else ""))


def call(client, method, path, token="", params=None, json_body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, f"{BASE}{path}", headers=headers, params=params, json=json_body)


def main() -> int:
    c = httpx.Client(timeout=20)
    r = call(c, "POST", "/api/auth/login", json_body={"username": "admin", "password": ""})
    ok = r.status_code == 200 and "access_token" in r.text
    check("PMT-AI2-S0-01", "登录", ok, f"HTTP {r.status_code}")
    token = r.json()["access_token"] if ok else ""

    # ---- 建项目 / 里程碑 / 工作包 / 任务 ----
    r = call(c, "POST", "/api/projects", token=token, json_body={"code": PROJ_CODE, "name": f"剧本2 {TS}"})
    pid = r.json().get("id", "") if r.status_code == 201 else ""
    check("PMT-AI2-S1-01", "建项目", r.status_code == 201, f"HTTP {r.status_code}")

    r = call(c, "POST", "/api/wbs/milestones", token=token, params={"project_id": pid},
             json_body={"code": "M2", "name": "开发实施", "status": "进行中", "owner": "Dr Ming"})
    mid = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/wbs/workpackages", token=token, params={"project_id": pid},
             json_body={"milestone_id": mid, "code": "WP2", "name": "核心功能开发"})
    wid = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/tasks", token=token, params={"project_id": pid}, json_body={
        "code": f"T2-{TS}", "title": "开发核心模块", "deliverables": "模块代码",
        "acceptance": "测试通过", "human_owner": "H-001", "ai_executor": "AI-PM-001",
        "priority": "P1", "milestone_id": mid, "work_package_id": wid})
    tid = r.json().get("id", "") if r.status_code == 201 else ""
    check("PMT-AI2-S1-02", "建任务", r.status_code == 201, f"HTTP {r.status_code}")

    # ---- 拆 3 个子任务 ----
    st = {}
    for code, title in (("ST-A", "模块A实现"), ("ST-B", "模块B实现"), ("ST-C", "模块C实现")):
        r = call(c, "POST", "/api/wbs/subtasks", token=token, params={"project_id": pid},
                 json_body={"task_id": tid, "code": code, "title": title, "assignee": "AI-PM-001"})
        st[code] = r.json().get("id", "") if r.status_code == 201 else ""
        check(f"PMT-AI2-S1-03-{code}", f"拆子任务 {code}", r.status_code == 201, f"HTTP {r.status_code}")

    # ---- ST-A 全链：证据 → 待办→进行中→待评审→通过→关闭 ----
    r = call(c, "POST", f"/api/wbs/subtasks/{st['ST-A']}/evidence", token=token, params={"project_id": pid},
             json_body={"paths": ["03_日志/任务台账/T2_模块A代码.docx"], "summary": "模块A完成"})
    check("PMT-AI2-S2-01", "ST-A 登记证据", r.status_code == 200, f"HTTP {r.status_code}")

    chain = ["进行中", "待评审", "通过", "关闭"]
    for i, target in enumerate(chain):
        r = call(c, "POST", f"/api/wbs/subtasks/{st['ST-A']}/transition", token=token,
                 params={"project_id": pid}, json_body={"target": target})
        check(f"PMT-AI2-S2-0{2 + i}", f"ST-A 推进→{target}", r.status_code == 200, f"HTTP {r.status_code}")

    # ---- ST-B 阻塞分支 ----
    r = call(c, "POST", f"/api/wbs/subtasks/{st['ST-B']}/transition", token=token,
             params={"project_id": pid}, json_body={"target": "阻塞"})
    check("PMT-AI2-S3-01", "ST-B 待办→阻塞", r.status_code == 200, f"HTTP {r.status_code}")
    r = call(c, "POST", f"/api/wbs/subtasks/{st['ST-B']}/transition", token=token,
             params={"project_id": pid}, json_body={"target": "进行中"})
    check("PMT-AI2-S3-02", "ST-B 阻塞→进行中", r.status_code == 200, f"HTTP {r.status_code}")

    # ---- ST-C 返工分支 ----
    r = call(c, "POST", f"/api/wbs/subtasks/{st['ST-C']}/transition", token=token,
             params={"project_id": pid}, json_body={"target": "进行中"})
    r = call(c, "POST", f"/api/wbs/subtasks/{st['ST-C']}/transition", token=token,
             params={"project_id": pid}, json_body={"target": "待评审"})
    check("PMT-AI2-S4-01", "ST-C 推进→待评审", r.status_code == 200, f"HTTP {r.status_code}")
    r = call(c, "POST", f"/api/wbs/subtasks/{st['ST-C']}/transition", token=token,
             params={"project_id": pid}, json_body={"target": "返工"})
    check("PMT-AI2-S4-02", "ST-C 待评审→返工", r.status_code == 200, f"HTTP {r.status_code}")
    r = call(c, "POST", f"/api/wbs/subtasks/{st['ST-C']}/transition", token=token,
             params={"project_id": pid}, json_body={"target": "进行中"})
    check("PMT-AI2-S4-03", "ST-C 返工→进行中", r.status_code == 200, f"HTTP {r.status_code}")

    # ---- 非法迁移与非法 target ----
    r = call(c, "POST", f"/api/wbs/subtasks/{st['ST-A']}/transition", token=token,
             params={"project_id": pid}, json_body={"target": "待办"})
    check("PMT-AI2-S5-01", "非法迁移 关闭→待办", r.status_code == 409, f"HTTP {r.status_code}")
    r = call(c, "POST", f"/api/wbs/subtasks/{st['ST-B']}/transition", token=token,
             params={"project_id": pid}, json_body={"target": "不存在"})
    check("PMT-AI2-S5-02", "非法 target 值", r.status_code == 422, f"HTTP {r.status_code}")

    # ---- 树查询验证子任务状态 ----
    r = call(c, "GET", "/api/wbs/tree", token=token, params={"project_id": pid})
    tree = r.json() if r.status_code == 200 else {}
    st_map = {}
    for m in tree.get("milestones", []):
        for w in m.get("work_packages", []):
            for t in w.get("tasks", []):
                for s in t.get("sub_tasks", []):
                    st_map[s["code"]] = s["status"]
    expect = {"ST-A": "关闭", "ST-B": "进行中", "ST-C": "进行中"}
    ok = r.status_code == 200 and all(st_map.get(k) == v for k, v in expect.items())
    check("PMT-AI2-S6-01", "树查询子任务状态正确", ok, f"实际={st_map}")

    # ---- 汇总 ----
    passed = sum(1 for x in RESULTS if x["pass"])
    failed = [x for x in RESULTS if not x["pass"]]
    print("\n" + "=" * 60)
    print(f"剧本2 完成：共 {len(RESULTS)} 项，PASS {passed}，FAIL {len(failed)}")
    for x in failed:
        print(f"  - {x['case']} {x['name']}: {x['detail']}")
    out = Path(__file__).resolve().parents[2] / "data" / "02_交付物" / "04_测试" / f"report_playbook2_{TS}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"script": "playbook2", "ts": TS, "project_code": PROJ_CODE, "project_id": pid,
                               "total": len(RESULTS), "passed": passed, "failed": len(failed), "results": RESULTS},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告：{out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
