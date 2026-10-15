"""UAT 批 2：US-04 计划与分解（WBS+任务卡）+ US-06 流程门禁与质量闸门。

用例来源：《PM-Collab 验收测试大纲（UAT）_V1.0.md》批 2。
运行（pm-collab/ 根）：.venv\\Scripts\\python tests\\e2e_ai\\playbook_uat_b2.py
数据卫生：临时 AI 成员用后即删；测试项目 TEST-B2-<ts> 留存。
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
PROJ_CODE = f"TEST-B2-{TS}"
AI_CODE = f"AI-B2-{TS}"
AI_USER = f"ai_b2_{TS}"
AI_PWD = "test-b2-2026"

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

    r = call(c, "POST", "/api/auth/login", json_body={"username": "admin", "password": ""})
    admin_token = r.json()["access_token"] if r.status_code == 200 else ""
    if not admin_token:
        print("[FATAL] admin 登录失败")
        return 1

    r = call(c, "POST", "/api/projects", token=admin_token,
             json_body={"code": PROJ_CODE, "name": f"UAT 批2 {TS}", "owner": "Dr Ming"})
    pid = r.json().get("id", "") if r.status_code == 201 else ""
    if not pid:
        print(f"[FATAL] 建项目失败 {r.status_code}")
        return 1
    print(f"[INFO] 测试项目 {PROJ_CODE} id={pid}")

    ai_member_id = ""
    r = call(c, "POST", "/api/members", token=admin_token, params={"project_id": pid},
             json_body={"code": AI_CODE, "name": "AI 批2测试（临时）", "member_type": "AI",
                        "username": AI_USER, "password": AI_PWD})
    ai_member_id = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/auth/login", json_body={"username": AI_USER, "password": AI_PWD})
    ai_token = r.json().get("access_token", "") if r.status_code == 200 else ""

    # ================= US-04 计划与分解 =================
    print("\n===== US-04 计划与分解（WBS + 任务卡） =====")

    # TEST-04-01 WBS 四层
    r = call(c, "POST", "/api/wbs/milestones", token=admin_token, params={"project_id": pid},
             json_body={"code": "M1", "name": "里程碑一", "status": "进行中"})
    m1 = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/wbs/workpackages", token=admin_token, params={"project_id": pid},
             json_body={"code": "WP1", "name": "工作包一", "milestone_id": m1, "status": "进行中"})
    wp1 = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T1-{TS}", "title": "产出需求规格书", "milestone_id": m1, "work_package_id": wp1,
                        "human_owner": "H-001", "ai_executor": "AI-PM-001", "priority": "P1"})
    t1 = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/wbs/subtasks", token=admin_token, params={"project_id": pid},
             json_body={"task_id": t1, "code": f"ST1-{TS}", "title": "整理干系人清单", "assignee": "AI-PM-001"})
    st1 = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "GET", "/api/wbs/tree", token=admin_token, params={"project_id": pid})
    tree = r.json() if r.status_code == 200 else {}
    ms = tree.get("milestones", [])
    has4 = bool(ms) and any(
        x.get("code") == "M1" and any(
            w.get("code") == "WP1" and any(
                t.get("code") == f"T1-{TS}" and len(t.get("sub_tasks", [])) == 1
                for t in w.get("tasks", []))
            for w in x.get("work_packages", []))
        for x in ms)
    check("TEST-04-01", "WBS 四层（里程碑→工作包→任务→子任务）", has4,
          f"HTTP {r.status_code} 四层完整={has4}", "P0")

    # TEST-04-02 任务卡 14 字段 + 初始状态
    r = call(c, "GET", f"/api/tasks/{t1}", token=admin_token, params={"project_id": pid})
    echo = r.json() if r.status_code == 200 else {}
    fields = ["code", "title", "deliverables", "acceptance", "human_owner", "ai_executor",
              "priority", "milestone", "work_package", "status", "inputs", "evidence", "summary"]
    ok = r.status_code == 200 and echo.get("status") == "待办" and echo.get("milestone") == "里程碑一" \
        and echo.get("work_package") == "工作包一"
    check("TEST-04-02", "任务卡字段创建且初始「待办」", ok,
          f"HTTP {r.status_code} status={echo.get('status')} milestone={echo.get('milestone')}", "P0")

    # TEST-04-03 合法迁移链：待办→进行中→待评审→通过→关闭
    r = call(c, "POST", f"/api/tasks/{t1}/transition", token=admin_token, params={"project_id": pid},
             json_body={"target": "进行中"})
    s1 = r.status_code
    r = call(c, "POST", f"/api/tasks/{t1}/evidence", token=admin_token, params={"project_id": pid},
             json_body={"paths": ["03_日志/任务台账/批2证据.docx"], "summary": "已完成并自检，交付需求规格书"})
    s2 = r.status_code
    r = call(c, "POST", f"/api/tasks/{t1}/transition", token=admin_token, params={"project_id": pid},
             json_body={"target": "待评审"})
    s3 = r.status_code
    r = call(c, "POST", f"/api/tasks/{t1}/transition", token=admin_token, params={"project_id": pid},
             json_body={"target": "通过"})
    s4 = r.status_code
    r = call(c, "POST", f"/api/tasks/{t1}/transition", token=admin_token, params={"project_id": pid},
             json_body={"target": "关闭"})
    s5 = r.status_code
    ok = [s1, s2, s3, s4, s5] == [200, 200, 200, 200, 200] and (r.json().get("status") if r.status_code == 200 else "") == "关闭"
    check("TEST-04-03", "合法迁移链全通（待办→…→关闭）", ok,
          f"状态码={[s1, s2, s3, s4, s5]} 终态={r.json().get('status') if r.status_code == 200 else '-'}", "P0")

    # TEST-04-04 非法迁移
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T2-{TS}", "title": "非法迁移任务", "milestone_id": m1, "work_package_id": wp1})
    t2 = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", f"/api/tasks/{t2}/transition", token=admin_token, params={"project_id": pid},
             json_body={"target": "关闭"})
    ok1 = r.status_code == 409
    r = call(c, "POST", f"/api/tasks/{t1}/transition", token=admin_token, params={"project_id": pid},
             json_body={"target": "待办"})
    ok2 = r.status_code == 409
    check("TEST-04-04", "非法迁移被拒（跳变 待办→关闭 / 倒退 关闭→待办）", ok1 and ok2,
          f"待办→关闭={r.status_code if ok1 else '?'} 关闭→待办 HTTP {r.status_code if ok2 else '?'}", "P0")

    # TEST-04-05 无证据不得置"待评审"
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T3-{TS}", "title": "证据前置任务", "milestone_id": m1, "work_package_id": wp1})
    t3 = r.json().get("id", "") if r.status_code == 201 else ""
    call(c, "POST", f"/api/tasks/{t3}/transition", token=admin_token, params={"project_id": pid},
         json_body={"target": "进行中"})
    r = call(c, "POST", f"/api/tasks/{t3}/transition", token=admin_token, params={"project_id": pid},
             json_body={"target": "待评审"})
    check("TEST-04-05", "无证据置「待评审」被拒", r.status_code == 422, f"HTTP {r.status_code}", "P0")

    # TEST-04-06 任务挂跨项目里程碑
    r = call(c, "GET", "/api/projects", token=admin_token)
    other_pid = next((p["id"] for p in (r.json() if r.status_code == 200 else [])
                      if p["id"] != pid and p.get("code") != PROJ_CODE), "")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T4-{TS}", "title": "跨项目任务", "milestone_id": other_pid})
    check("TEST-04-06", "任务挂跨项目里程碑被拒", r.status_code == 404, f"HTTP {r.status_code}", "P1")

    # TEST-04-07 层级冲突：指定 MB 里程碑 + 挂 MA 的工作包
    r = call(c, "POST", "/api/wbs/milestones", token=admin_token, params={"project_id": pid},
             json_body={"code": "MA", "name": "里程碑A", "status": "进行中"})
    ma = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/wbs/milestones", token=admin_token, params={"project_id": pid},
             json_body={"code": "MB", "name": "里程碑B", "status": "进行中"})
    mb = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/wbs/workpackages", token=admin_token, params={"project_id": pid},
             json_body={"code": "WPA", "name": "工作包A", "milestone_id": ma, "status": "进行中"})
    wpa = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T5-{TS}", "title": "冲突任务", "milestone_id": mb, "work_package_id": wpa})
    check("TEST-04-07", "任务指定里程碑与工作包冲突被拒", r.status_code == 409 and "层级归属冲突" in r.text,
          f"HTTP {r.status_code} {r.text[:80]}", "P1")

    # TEST-04-08 仅给工作包自动继承里程碑
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T6-{TS}", "title": "自动继承任务", "work_package_id": wpa})
    t6 = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "GET", f"/api/tasks/{t6}", token=admin_token, params={"project_id": pid})
    e6 = r.json() if r.status_code == 200 else {}
    check("TEST-04-08", "仅填工作包自动继承里程碑", r.status_code == 200 and e6.get("milestone_id") == ma,
          f"HTTP {r.status_code} milestone={e6.get('milestone')} 继承一致={e6.get('milestone_id') == ma}", "P1")

    # ================= US-06 流程门禁与质量闸门 =================
    print("\n===== US-06 流程门禁与质量闸门 =====")

    r = call(c, "GET", "/api/process/instance", token=admin_token, params={"project_id": pid})
    ok = r.status_code == 200 and r.json().get("stage") == "S1"
    check("TEST-06-01", "新项目流程实例 S1", ok, f"HTTP {r.status_code} stage={r.json().get('stage') if r.status_code == 200 else '-'}", "P0")
    r = call(c, "GET", "/api/process/gates", token=admin_token, params={"project_id": pid})
    gates = r.json() if r.status_code == 200 else []
    check("TEST-06-01", "4 门禁就绪", [g.get("gate_no") for g in gates] == ["①", "②", "③", "④"],
          f"门禁={[g.get('gate_no') for g in gates]}", "P0")

    r = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S2"})
    ok1 = r.status_code == 403
    r = call(c, "GET", "/api/checkpoints", token=admin_token, params={"project_id": pid})
    cp = any("缺少门禁①" in (x.get("content", "") + x.get("category", "")) for x in (r.json() if r.status_code == 200 else []))
    check("TEST-06-02", "未签字 advance 被拦截并生成审批卡点", ok1 and cp,
          f"HTTP {r.status_code if ok1 else '?'} 卡点含「缺少门禁①」={cp}", "P0")

    r = call(c, "POST", "/api/process/gates/sign", token=admin_token, params={"project_id": pid},
             json_body={"gate_no": "①", "decision": "通过", "signed_by": "H", "opinion": "需求评审通过"})
    r2 = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S2"})
    check("TEST-06-03", "人类签门禁①后推进 S2", r.status_code == 200 and r2.status_code == 200 and r2.json().get("stage") == "S2",
          f"sign={r.status_code} advance={r2.status_code} stage={r2.json().get('stage') if r2.status_code == 200 else '-'}", "P0")

    r = call(c, "POST", "/api/process/gates/sign", token=ai_token, params={"project_id": pid},
             json_body={"gate_no": "②", "decision": "通过", "signed_by": AI_CODE})
    check("TEST-06-04", "AI 代签门禁被拒", r.status_code == 403 and "人类" in r.text, f"HTTP {r.status_code} {r.text[:80]}", "P0")

    r = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S4"})
    check("TEST-06-05", "阶段跳过被拒（S2→S4）", r.status_code == 409, f"HTTP {r.status_code}", "P0")

    # 推进到 S6：S2→S3 →签②→ S4→S5 →签③→ S6
    r1 = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S3"})
    r2 = call(c, "POST", "/api/process/gates/sign", token=admin_token, params={"project_id": pid},
              json_body={"gate_no": "②", "decision": "通过", "signed_by": "H", "opinion": "设计评审通过"})
    r3 = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S4"})
    r4 = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S5"})
    r5 = call(c, "POST", "/api/process/gates/sign", token=admin_token, params={"project_id": pid},
              json_body={"gate_no": "③", "decision": "通过", "signed_by": "H", "opinion": "代码评审通过"})
    r6 = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S6"})
    ok = [r1.status_code, r2.status_code, r3.status_code, r4.status_code, r5.status_code, r6.status_code] == [200] * 6
    check("TEST-06-06", "推进到 S6（签②③）", ok,
          f"状态码={[r1.status_code, r2.status_code, r3.status_code, r4.status_code, r5.status_code, r6.status_code]}", "P0")

    r = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S7"})
    check("TEST-06-06", "测试未通过不得进入验收（S6→S7 阻塞）", r.status_code == 422, f"HTTP {r.status_code}", "P0")

    r = call(c, "POST", "/api/process/test-result", token=admin_token, params={"project_id": pid},
             json_body={"passed": False, "report_path": "02_交付物/04_测试/批2未通过.md"})
    r2 = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S7"})
    ok1 = r.status_code == 200 and r2.status_code == 422
    r3 = call(c, "POST", "/api/process/test-result", token=admin_token, params={"project_id": pid},
              json_body={"passed": True, "report_path": "02_交付物/04_测试/批2通过.md"})
    r4 = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S7"})
    ok2 = r3.status_code == 200 and r4.status_code == 200 and r4.json().get("stage") == "S7"
    check("TEST-06-07", "测试未通过阻塞推进 / 通过后放行验收", ok1 and ok2,
          f"未通过登记={r.status_code} 推进={r2.status_code} | 通过登记={r3.status_code} 推进={r4.status_code} stage={r4.json().get('stage') if r4.status_code == 200 else '-'}", "P1")

    # ---------- 清理 ----------
    if ai_member_id:
        r = call(c, "DELETE", f"/api/members/{ai_member_id}", token=admin_token, params={"project_id": pid})
        print(f"[INFO] 清理临时 AI 成员 {AI_CODE} -> HTTP {r.status_code}")

    # ---------- 汇总 ----------
    passed = sum(1 for x in RESULTS if x["pass"])
    failed = [x for x in RESULTS if not x["pass"]]
    print("\n" + "=" * 76)
    print(f"UAT 批2 执行完成：共 {len(RESULTS)} 项，PASS {passed}，FAIL {len(failed)}")
    for x in failed:
        print(f"  - {x['case']} {x['name']} [{x['level']}]: {x['detail']}")
    summary = {"script": "playbook_uat_b2", "ts": TS, "project_code": PROJ_CODE, "project_id": pid,
               "total": len(RESULTS), "passed": passed, "failed": len(failed), "results": RESULTS}
    out = Path(__file__).resolve().parents[2] / "data" / "02_交付物" / "04_测试" / f"report_uat_b2_{TS}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入：{out}")
    print("=" * 76)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
