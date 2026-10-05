"""剧本1 端到端执行脚本：AI 管理一个项目的完整生命周期。

运行方式（项目根 pm-collab/ 下）：
    .venv\\Scripts\\python tests\\e2e_ai\\playbook1.py

对应用例：PM-Collab AI功能测试用例_剧本1_V1.0.md（40 条，本脚本执行其中自动项）
被测实例：http://127.0.0.1:8731（运行中）
数据卫生：模拟项目 T-AI-<ts> 与默认项目隔离；临时 AI 成员用后即删。
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8731"
TS = datetime.datetime.now().strftime("%H%M%S")
PROJ_CODE = f"T-AI-{TS}"
PROJ_NAME = f"AI 端到端剧本1 {TS}"
DONE_DIR = Path(__file__).resolve().parents[2] / "data" / "交接区" / "完成"

RESULTS: list[dict] = []


def check(case_id: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"case": case_id, "name": name, "pass": ok, "detail": detail})
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {case_id} {name}" + (f" | {detail}" if detail else ""))


def call(
    client: httpx.Client,
    method: str,
    path: str,
    token: str = "",
    params: dict | None = None,
    json_body: dict | None = None,
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, f"{BASE}{path}", headers=headers, params=params, json=json_body)


def main() -> int:
    c = httpx.Client(timeout=20)
    token = ""

    # ---------------- S1 登录 ----------------
    r = call(c, "POST", "/api/auth/login", json_body={"username": "admin", "password": "REMOVED-FOR-OPENSOURCE"})
    ok = r.status_code == 200 and "access_token" in r.text
    check("PMT-AI1-S1-01", "正确账号登录", ok, f"HTTP {r.status_code}")
    if ok:
        token = r.json()["access_token"]

    r = call(c, "POST", "/api/auth/login", json_body={"username": "admin", "password": "wrong-pass"})
    check("PMT-AI1-S1-02", "错误密码登录", r.status_code == 401, f"HTTP {r.status_code}")

    r = call(c, "POST", "/api/auth/login", json_body={"password": "REMOVED-FOR-OPENSOURCE"})
    check("PMT-AI1-S1-03", "登录缺字段", r.status_code == 422, f"HTTP {r.status_code}")

    r = call(c, "GET", "/api/tasks")
    check("PMT-AI1-S1-04", "无令牌访问业务接口", r.status_code == 401, f"HTTP {r.status_code}")

    # ---------------- S2 建项目 ----------------
    r = call(c, "POST", "/api/projects", token=token, json_body={
        "code": PROJ_CODE, "name": PROJ_NAME,
        "description": "剧本1 端到端测试模拟项目（AI 全流程）", "owner": "Dr Ming"})
    ok = r.status_code == 201 and "id" in r.text
    check("PMT-AI1-S2-01", "新建项目成功", ok, f"HTTP {r.status_code} {r.text[:160]}")
    pid = r.json().get("id", "") if ok else ""

    r = call(c, "GET", "/api/process/instance", token=token, params={"project_id": pid})
    ok = r.status_code == 200 and r.json().get("stage") == "S1" and r.json().get("required_gate") == "①"
    check("PMT-AI1-S2-02", "新项目自动初始化流程实例", ok,
          f"HTTP {r.status_code} stage={r.json().get('stage') if r.status_code == 200 else '-'}")

    r = call(c, "GET", "/api/process/gates", token=token, params={"project_id": pid})
    gates = r.json() if r.status_code == 200 else []
    ok = r.status_code == 200 and [g["gate_no"] for g in gates] == ["①", "②", "③", "④"]
    check("PMT-AI1-S2-03", "新项目自动初始化 4 门禁", ok, f"HTTP {r.status_code} 门禁={[g.get('gate_no') for g in gates]}")

    r = call(c, "POST", "/api/projects", token=token, json_body={"code": PROJ_CODE, "name": "dup"})
    check("PMT-AI1-S2-04", "项目 code 重复", r.status_code == 409, f"HTTP {r.status_code}")

    r = call(c, "POST", "/api/projects", token=token, json_body={"code": f"T-X-{TS}"})
    check("PMT-AI1-S2-05", "建项目缺必填 name", r.status_code == 422, f"HTTP {r.status_code}")

    # ---------------- S3 建里程碑 ----------------
    r = call(c, "POST", "/api/wbs/milestones", token=token, params={"project_id": pid},
             json_body={"code": "M1", "name": "需求与方案", "status": "进行中", "owner": "Dr Ming"})
    ok = r.status_code == 201 and "id" in r.text
    check("PMT-AI1-S3-01", "指定项目建里程碑", ok, f"HTTP {r.status_code}")
    mid = r.json().get("id", "") if ok else ""

    r = call(c, "POST", "/api/wbs/milestones", token=token, params={"project_id": pid},
             json_body={"code": "M1", "name": "重复"})
    check("PMT-AI1-S3-02", "里程碑 code 重复", r.status_code == 409, f"HTTP {r.status_code}")

    # S3-03 回退默认项目 → L1（避免污染默认项目），本脚本不执行

    # ---------------- S4 建工作包 ----------------
    r = call(c, "POST", "/api/wbs/workpackages", token=token, params={"project_id": pid},
             json_body={"milestone_id": mid, "code": "WP1", "name": "需求调研", "status": "进行中"})
    ok = r.status_code == 201 and "id" in r.text
    check("PMT-AI1-S4-01", "带 milestone_id 建工作包", ok, f"HTTP {r.status_code}")
    wid = r.json().get("id", "") if ok else ""

    r = call(c, "POST", "/api/wbs/workpackages", token=token, params={"project_id": pid},
             json_body={"code": "WPX", "name": "缺里程碑"})
    check("PMT-AI1-S4-02", "工作包缺 milestone_id", r.status_code == 422, f"HTTP {r.status_code}")

    r = call(c, "POST", "/api/wbs/workpackages", token=token, params={"project_id": pid},
             json_body={"milestone_id": mid, "code": "WP1", "name": "重复"})
    check("PMT-AI1-S4-03", "工作包 code 重复", r.status_code == 409, f"HTTP {r.status_code}")

    # ---------------- S5 建任务 ----------------
    # 注：实测任务编号查重未按 project_id 过滤（全局唯一），与"项目内唯一"规则存在偏差；
    # 脚本按指导书建议采用时间戳编号（模拟 AI 查重后换号），编号偏差另作缺陷记录。
    t_code = f"T1-{TS}"
    task_body = {
        "code": t_code, "title": "产出需求规格书", "inputs": "访谈记录",
        "deliverables": "需求规格书.docx", "acceptance": "评审通过",
        "human_owner": "H-001", "ai_executor": "AI-PM-001", "priority": "P1",
        "milestone_id": mid, "work_package_id": wid,
    }
    r = call(c, "POST", "/api/tasks", token=token, params={"project_id": pid}, json_body=task_body)
    ok = r.status_code == 201 and r.json().get("status") == "待办"
    check("PMT-AI1-S5-01", "建任务并关联里程碑/工作包", ok, f"HTTP {r.status_code} status={r.json().get('status') if r.status_code == 201 else '-'}")
    tid = r.json().get("id", "") if ok else ""

    r = call(c, "POST", "/api/tasks", token=token, params={"project_id": pid}, json_body=task_body)
    check("PMT-AI1-S5-02", "任务 code 重复", r.status_code == 409, f"HTTP {r.status_code}")

    if ok:
        body = r.json() if r.status_code == 201 else {}
        got = {k: body.get(k) for k in ("title", "deliverables", "acceptance", "human_owner", "ai_executor", "priority")}
        # 用首次创建响应回显校验（重复请求 409 不返回内容）
        r0 = call(c, "GET", f"/api/tasks/{tid}", token=token, params={"project_id": pid})
        echo = r0.json() if r0.status_code == 200 else {}
        ok = all(echo.get(k) == task_body.get(k) for k in ("title", "deliverables", "acceptance", "human_owner", "ai_executor", "priority"))
        check("PMT-AI1-S5-03", "任务字段回显一致", ok, f"HTTP {r0.status_code} echo={got}")

    bad = dict(task_body, code=f"TBAD-{TS}", priority="P9")
    r = call(c, "POST", "/api/tasks", token=token, params={"project_id": pid}, json_body=bad)
    check("PMT-AI1-S5-04", "非法 priority", r.status_code == 422, f"HTTP {r.status_code}")

    # ---------------- S6 拆子任务 ----------------
    r = call(c, "POST", "/api/wbs/subtasks", token=token, params={"project_id": pid},
             json_body={"task_id": tid, "code": f"ST1-{TS}", "title": "整理干系人清单",
                        "assignee": "AI-PM-001", "priority": "P2"})
    ok = r.status_code == 201 and "id" in r.text
    check("PMT-AI1-S6-01", "带 task_id 拆子任务", ok, f"HTTP {r.status_code}")
    sid = r.json().get("id", "") if ok else ""

    r = call(c, "POST", "/api/wbs/subtasks", token=token, params={"project_id": pid},
             json_body={"code": "STX", "title": "缺任务"})
    check("PMT-AI1-S6-02", "子任务缺 task_id", r.status_code == 422, f"HTTP {r.status_code}")

    r = call(c, "GET", "/api/wbs/tree", token=token, params={"project_id": pid})
    tree = r.json() if r.status_code == 200 else {}
    ms_nodes = tree.get("milestones", [])
    has4 = (r.status_code == 200 and any(
        m.get("code") == "M1" and any(
            w.get("code") == "WP1" and any(
                t.get("code") == t_code and len(t.get("sub_tasks", [])) == 1 and t["sub_tasks"][0]["code"] == f"ST1-{TS}"
                for t in w.get("tasks", []))
            for w in m.get("work_packages", []))
        for m in ms_nodes))
    check("PMT-AI1-S6-03", "WBS 树四层完整", has4, f"HTTP {r.status_code} 里程碑数={len(ms_nodes)}")

    # ---------------- S8 状态推进（S8-03 证据前置先于 S7 登记） ----------------
    r = call(c, "POST", f"/api/wbs/subtasks/{sid}/transition", token=token, params={"project_id": pid},
             json_body={"target": "进行中"})
    check("PMT-AI1-S8-01", "子任务 待办→进行中", r.status_code == 200, f"HTTP {r.status_code}")

    r = call(c, "POST", f"/api/tasks/{tid}/transition", token=token, params={"project_id": pid},
             json_body={"target": "进行中"})
    check("PMT-AI1-S8-02", "任务 待办→进行中", r.status_code == 200, f"HTTP {r.status_code}")

    r = call(c, "POST", f"/api/tasks/{tid}/transition", token=token, params={"project_id": pid},
             json_body={"target": "待评审"})
    check("PMT-AI1-S8-03", "无证据置“待评审”被拒", r.status_code == 422, f"HTTP {r.status_code}")

    # ---------------- S7 登记证据 ----------------
    r = call(c, "POST", f"/api/tasks/{tid}/evidence", token=token, params={"project_id": pid},
             json_body={"paths": ["03_日志/任务台账/T1_需求规格书.docx"], "summary": "已上传并自审"})
    check("PMT-AI1-S7-01", "任务登记证据", r.status_code == 200 and "evidence" in r.text, f"HTTP {r.status_code}")

    r = call(c, "POST", f"/api/tasks/{tid}/evidence", token=token, params={"project_id": pid},
             json_body={"summary": "缺证据路径"})
    check("PMT-AI1-S7-02", "证据缺 paths 字段", r.status_code == 422, f"HTTP {r.status_code}")

    # 继续 S8
    r = call(c, "POST", f"/api/tasks/{tid}/transition", token=token, params={"project_id": pid},
             json_body={"target": "待评审"})
    ok = r.status_code == 200 and r.json().get("status") == "待评审"
    check("PMT-AI1-S8-04", "有证据后置“待评审”", ok, f"HTTP {r.status_code}")
    r = call(c, "GET", "/api/checkpoints", token=token)
    cp_ok = r.status_code == 200 and "审批请求" in r.text
    check("PMT-AI1-S8-04", "置待评审生成审批卡点", cp_ok, f"HTTP {r.status_code} checkpoints含审批请求={cp_ok}")

    r = call(c, "POST", f"/api/tasks/{tid}/transition", token=token, params={"project_id": pid},
             json_body={"target": "关闭"})
    check("PMT-AI1-S8-05", "非法迁移 待评审→关闭", r.status_code == 409, f"HTTP {r.status_code}")

    # ---------------- S9 流程与门禁 ----------------
    r = call(c, "POST", "/api/process/advance", token=token, params={"project_id": pid}, json_body={"target": "S2"})
    ok = r.status_code == 403
    check("PMT-AI1-S9-01", "未签字 advance 被拦截", ok, f"HTTP {r.status_code}")

    r = call(c, "POST", "/api/process/gates/sign", token=token, params={"project_id": pid},
             json_body={"gate_no": "①", "decision": "通过", "signed_by": "H", "opinion": "需求条目齐备，评审通过"})
    ok = r.status_code == 200 and r.json().get("signed_by")
    check("PMT-AI1-S9-02", "人类身份签门禁①", ok, f"HTTP {r.status_code} {r.text[:120]}")

    # S9-03 AI 代签：临时 AI 成员
    r = call(c, "POST", "/api/members", token=token, json_body={
        "code": "AI-QA-TEST", "name": "QA-AI 测试实例（临时）", "member_type": "AI",
        "username": "ai_qatest", "password": "test-2026"})
    ai_member_id = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/auth/login", json_body={"username": "ai_qatest", "password": "test-2026"})
    ai_token = r.json().get("access_token", "") if r.status_code == 200 else ""
    r = call(c, "POST", "/api/process/gates/sign", token=ai_token, params={"project_id": pid},
             json_body={"gate_no": "②", "decision": "通过", "signed_by": "AI-PM-001"})
    check("PMT-AI1-S9-03", "AI 身份签门禁被拒", r.status_code == 403, f"HTTP {r.status_code} {r.text[:120]}")
    if ai_member_id:
        r = call(c, "DELETE", f"/api/members/{ai_member_id}", token=token)
        print(f"[INFO] 清理临时 AI 成员 AI-QA-TEST -> HTTP {r.status_code}")

    r = call(c, "POST", "/api/process/advance", token=token, params={"project_id": pid}, json_body={"target": "S2"})
    ok = r.status_code == 200 and r.json().get("stage") == "S2"
    check("PMT-AI1-S9-04", "签字后 advance 放行", ok, f"HTTP {r.status_code} stage={r.json().get('stage') if r.status_code == 200 else '-'}")

    # ---------------- S10 交接闭环 ----------------
    r = call(c, "POST", f"/api/handoff/feed/{tid}", token=token, params={"project_id": pid, "receiver": "AI-PM-001"})
    ok = r.status_code == 200 and r.json().get("status") == "已投喂" and Path(r.json().get("file", "")).exists()
    order_code = r.json().get("order", "") if ok else ""
    check("PMT-AI1-S10-01", "feed 派单", ok, f"HTTP {r.status_code} status={r.json().get('status') if r.status_code == 200 else '-'}")
    # feed 返回的是交接单 code（HO-T1），按项目反查 UUID 作为 order_id
    # DEF-02 回归验证：feed 创建的交接单须继承 project_id，按项目过滤必须可见
    order_id = ""
    if order_code:
        r = call(c, "GET", "/api/handoff", token=token, params={"project_id": pid})
        orders = r.json() if r.status_code == 200 else []
        order_id = next((o["id"] for o in orders if o.get("code") == order_code), "")
        check("PMT-AI1-DEF02", "DEF-02 回归：交接单按项目过滤可见", bool(order_id),
              f"code={order_code} 命中={bool(order_id)}")
        if not order_id:  # 全局兜底，避免级联失败
            r = call(c, "GET", "/api/handoff", token=token)
            order_id = next((o["id"] for o in (r.json() if r.status_code == 200 else []) if o.get("code") == order_code), "")

    r = call(c, "POST", f"/api/handoff/{order_id}/close", token=token, params={"project_id": pid})
    check("PMT-AI1-S10-04", "交接单非法迁移（已投喂→闭环）", r.status_code == 409, f"HTTP {r.status_code}")

    # 模拟 AI 回写完成摘要（写入 完成/ 目录）
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    done_file = DONE_DIR / f"{t_code}_完成_产出需求规格书_V1.md"
    done_file.write_text(
        f"任务编号: {t_code}\n执行者: AI-PM-001\n"
        "证据路径: 03_日志/任务台账/T1_需求规格书.docx\n"
        "交付路径: 02_交付物/01_需求/T1_需求规格书.docx\n版本: V1.0\n\n"
        "已完成需求调研与干系人访谈，产出需求规格书草稿，自检通过。\n",
        encoding="utf-8")
    r = call(c, "POST", f"/api/handoff/recycle/{order_id}", token=token, params={"project_id": pid})
    body = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and body.get("status") == "已回收" and body.get("ledger")
    check("PMT-AI1-S10-02", "recycle 回收", ok,
          f"HTTP {r.status_code} status={body.get('status')} task_status={body.get('task_status')} ledger={bool(body.get('ledger'))}")

    r = call(c, "POST", f"/api/handoff/{order_id}/close", token=token, params={"project_id": pid})
    ok = r.status_code == 200 and r.json().get("status") == "已闭环"
    check("PMT-AI1-S10-03", "close 闭环", ok, f"HTTP {r.status_code}")

    r = call(c, "POST", f"/api/handoff/{order_id}/transition", token=token, params={"project_id": pid},
             json_body={"target": "已投喂"})
    check("PMT-AI1-S10-04", "交接单非法迁移（已闭环→已投喂）", r.status_code == 409, f"HTTP {r.status_code}")

    # ---------------- S11 报表与审计 ----------------
    r = call(c, "GET", "/api/report/logs", token=token, params={"project_id": pid})
    keywords = ["创建任务卡", "登记证据", "任务状态迁移", "门禁①需求评审签字", "投喂任务卡", "回收完成摘要", "交接单闭环"]
    missing = [k for k in keywords if k not in r.text]
    check("PMT-AI1-S11-01", "审计日志覆盖全部写操作", r.status_code == 200 and not missing,
          f"HTTP {r.status_code} 缺失关键词={missing or '无'}")

    r = call(c, "GET", "/api/report/metrics", token=token, params={"project_id": pid})
    ok_m = r.status_code == 200
    r = call(c, "GET", "/api/report/latest", token=token, params={"project_id": pid})
    ok_l = r.status_code == 200
    check("PMT-AI1-S11-02", "报表数据可访问", ok_m and ok_l, f"metrics={ok_m} latest={ok_l}")

    r = call(c, "GET", "/api/report/heartbeat")
    check("PMT-AI1-S11-03", "健康检查", r.status_code == 200, f"HTTP {r.status_code}")

    # ---------------- 汇总 ----------------
    passed = sum(1 for x in RESULTS if x["pass"])
    failed = [x for x in RESULTS if not x["pass"]]
    total = len(RESULTS)
    print("\n" + "=" * 72)
    print(f"剧本1 执行完成：共 {total} 项，PASS {passed}，FAIL {len(failed)}，覆盖率（用例清单 40 条中执行 {total} 条）")
    if failed:
        print("失败明细：")
        for x in failed:
            print(f"  - {x['case']} {x['name']}: {x['detail']}")
    summary = {
        "script": "playbook1", "ts": TS, "project_code": PROJ_CODE, "project_id": pid,
        "total": total, "passed": passed, "failed": len(failed),
        "results": RESULTS,
    }
    out_path = Path(__file__).resolve().parents[2] / "data" / "02_交付物" / "04_测试" / f"report_playbook1_{TS}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入：{out_path}")
    print("=" * 72)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
