"""剧本3 端到端执行脚本：多项目并发与隔离。

运行：.venv\\Scripts\\python tests\\e2e_ai\\playbook3.py
对应用例：PMT-AI3-*（多项目隔离专项；含 DEF-01 回归：任务编号项目内唯一）
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8731"
TS = datetime.datetime.now().strftime("%H%M%S")
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
    check("PMT-AI3-S0-01", "登录", ok, f"HTTP {r.status_code}")
    token = r.json()["access_token"] if ok else ""

    # ---- 建项目 A、B ----
    pa = call(c, "POST", "/api/projects", token=token, json_body={"code": f"T-AI3A-{TS}", "name": f"剧本3-A {TS}"})
    pb = call(c, "POST", "/api/projects", token=token, json_body={"code": f"T-AI3B-{TS}", "name": f"剧本3-B {TS}"})
    pid_a = pa.json().get("id", "") if pa.status_code == 201 else ""
    pid_b = pb.json().get("id", "") if pb.status_code == 201 else ""
    check("PMT-AI3-S1-01", "建项目 A/B", pa.status_code == 201 and pb.status_code == 201,
          f"A={pa.status_code} B={pb.status_code}")

    # ---- DEF-01 回归：两项目可复用同一任务编号 ----
    shared = {"code": "T-SHARED", "title": "共享编号任务", "deliverables": "x", "acceptance": "y",
              "human_owner": "H-001", "ai_executor": "AI-PM-001", "priority": "P2"}
    ra = call(c, "POST", "/api/tasks", token=token, params={"project_id": pid_a}, json_body=shared)
    rb = call(c, "POST", "/api/tasks", token=token, params={"project_id": pid_b}, json_body=shared)
    check("PMT-AI3-S2-01", "DEF-01 回归：A/B 建同 code 任务均成功",
          ra.status_code == 201 and rb.status_code == 201, f"A={ra.status_code} B={rb.status_code} {rb.text[:120]}")
    ra2 = call(c, "POST", "/api/tasks", token=token, params={"project_id": pid_a}, json_body=shared)
    rb2 = call(c, "POST", "/api/tasks", token=token, params={"project_id": pid_b}, json_body=shared)
    check("PMT-AI3-S2-02", "A 内重复 code → 409", ra2.status_code == 409, f"HTTP {ra2.status_code}")
    check("PMT-AI3-S2-03", "B 内重复 code → 409", rb2.status_code == 409, f"HTTP {rb2.status_code}")

    # ---- 里程碑：两项目可同 code ----
    m_body = {"code": "M-SHARED", "name": "共享里程碑", "status": "进行中", "owner": "Dr Ming"}
    ma = call(c, "POST", "/api/wbs/milestones", token=token, params={"project_id": pid_a}, json_body=m_body)
    mb = call(c, "POST", "/api/wbs/milestones", token=token, params={"project_id": pid_b}, json_body=m_body)
    mid_a = ma.json().get("id", "") if ma.status_code == 201 else ""
    mid_b = mb.json().get("id", "") if mb.status_code == 201 else ""
    check("PMT-AI3-S3-01", "A/B 建同 code 里程碑均成功", ma.status_code == 201 and mb.status_code == 201,
          f"A={ma.status_code} B={mb.status_code}")

    # ---- 跨项目引用拒绝：A 的工作包挂 B 的里程碑 ----
    r = call(c, "POST", "/api/wbs/workpackages", token=token, params={"project_id": pid_a},
             json_body={"milestone_id": mid_b, "code": "WP-X", "name": "跨项目工作包"})
    check("PMT-AI3-S3-02", "跨项目引用里程碑被拒", r.status_code == 404, f"HTTP {r.status_code} {r.text[:100]}")

    # ---- 隔离查询：A 的任务列表不含 B 的任务 ----
    r = call(c, "GET", "/api/tasks", token=token, params={"project_id": pid_a})
    codes_a = [t.get("code") for t in (r.json() if r.status_code == 200 else [])]
    r = call(c, "GET", "/api/tasks", token=token, params={"project_id": pid_b})
    codes_b = [t.get("code") for t in (r.json() if r.status_code == 200 else [])]
    ok = "T-SHARED" in codes_a and "T-SHARED" in codes_b and len(codes_a) == 1 and len(codes_b) == 1
    check("PMT-AI3-S4-01", "任务列表项目隔离", ok, f"A={codes_a} B={codes_b}")

    r = call(c, "GET", "/api/wbs/tree", token=token, params={"project_id": pid_a})
    tree_a = r.json() if r.status_code == 200 else {}
    r = call(c, "GET", "/api/wbs/tree", token=token, params={"project_id": pid_b})
    tree_b = r.json() if r.status_code == 200 else {}
    def codes_of(tree):
        return {m.get("code") for m in tree.get("milestones", [])}
    ok = codes_of(tree_a) == {"M-SHARED"} and codes_of(tree_b) == {"M-SHARED"}
    check("PMT-AI3-S4-02", "WBS 树项目隔离（各自仅含自身里程碑）", ok, f"A={codes_of(tree_a)} B={codes_of(tree_b)}")

    # ---- 交接隔离：A 的交接单在 A 可见、在 B 不可见 ----
    r = call(c, "POST", f"/api/handoff/feed/{ra.json().get('id','')}", token=token,
             params={"project_id": pid_a, "receiver": "AI-PM-001"})
    order_code = r.json().get("order", "") if r.status_code == 200 else ""
    r = call(c, "GET", "/api/handoff", token=token, params={"project_id": pid_a})
    hit_a = any(o.get("code") == order_code for o in (r.json() if r.status_code == 200 else []))
    r = call(c, "GET", "/api/handoff", token=token, params={"project_id": pid_b})
    hit_b = any(o.get("code") == order_code for o in (r.json() if r.status_code == 200 else []))
    check("PMT-AI3-S5-01", "交接单隔离（A 可见、B 不可见）", bool(order_code) and hit_a and not hit_b,
          f"order={order_code} A可见={hit_a} B可见={hit_b}")

    # ---- 门禁隔离：B 未签字 advance 仍拦截（不受 A 签字影响） ----
    r = call(c, "POST", "/api/process/advance", token=token, params={"project_id": pid_b}, json_body={"target": "S2"})
    check("PMT-AI3-S6-01", "门禁隔离：B 未签字 advance 拦截", r.status_code == 403, f"HTTP {r.status_code}")
    r = call(c, "POST", "/api/process/gates/sign", token=token, params={"project_id": pid_a},
             json_body={"gate_no": "①", "decision": "通过", "signed_by": "H"})
    r = call(c, "POST", "/api/process/advance", token=token, params={"project_id": pid_b}, json_body={"target": "S2"})
    check("PMT-AI3-S6-02", "A 签字不影响 B（B 仍 403）", r.status_code == 403, f"HTTP {r.status_code}")

    # ---- 汇总 ----
    passed = sum(1 for x in RESULTS if x["pass"])
    failed = [x for x in RESULTS if not x["pass"]]
    print("\n" + "=" * 60)
    print(f"剧本3 完成：共 {len(RESULTS)} 项，PASS {passed}，FAIL {len(failed)}")
    for x in failed:
        print(f"  - {x['case']} {x['name']}: {x['detail']}")
    out = Path(__file__).resolve().parents[2] / "data" / "02_交付物" / "04_测试" / f"report_playbook3_{TS}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"script": "playbook3", "ts": TS, "project_a": pid_a, "project_b": pid_b,
                               "total": len(RESULTS), "passed": passed, "failed": len(failed), "results": RESULTS},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告：{out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
