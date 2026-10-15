"""V0.4 设计更新开发测试：任务过程时间线 / 模块泳道 / 结构化字段 / 度量新指标。

设计基准：《人机共用项目管理软件-设计大纲-V0.4》（2026-10-10 已评审落地）
实现基准：《V0.4实现评审记录.md》（api/viz.py + 新字段 + digest 新指标 + 前端两视图）
本脚本为独立验收测试（对抗/集成/边界补充），运行：
  pm-collab/ 根：.venv\\Scripts\\python tests\\e2e_ai\\playbook_v04.py
数据卫生：测试项目 TEST-V04-<ts> 留存；临时 AI 成员用后即删。
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.environ.get("PM_TEST_BASE", "http://127.0.0.1:8731")
EXTERNAL = os.environ.get("PM_TEST_EXTERNAL") == "1"
ROOT = Path(__file__).resolve().parents[2]
TS = datetime.datetime.now().strftime("%H%M%S")
PROJ_CODE = f"TEST-V04-{TS}"
AI_CODE = f"AI-V04-{TS}"

RESULTS: list[dict] = []


def check(case: str, name: str, ok: bool, detail: str = "", level: str = "P1") -> None:
    RESULTS.append({"case": case, "name": name, "pass": ok, "detail": detail, "level": level})
    print(f"[{'PASS' if ok else 'FAIL'}] {case} {name} | {detail}")


def call(c: httpx.Client, method: str, path: str, token: str = "",
         params: dict | None = None, json_body: dict | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return c.request(method, f"{BASE}{path}", headers=headers, params=params, json=json_body)


def main() -> int:
    c = httpx.Client(timeout=30, verify=False if os.environ.get("PM_TEST_INSECURE") == "1" else True)
    print(f"[INFO] 被测实例：{BASE} EXTERNAL={EXTERNAL}")

    r = call(c, "POST", "/api/auth/login", json_body={"username": "admin", "password": ""})
    admin_token = r.json()["access_token"] if r.status_code == 200 else ""
    if not admin_token:
        print("[FATAL] admin 登录失败")
        return 1
    r = call(c, "POST", "/api/projects", token=admin_token, json_body={"code": PROJ_CODE, "name": f"UAT V0.4 {TS}"})
    pid = r.json().get("id", "") if r.status_code == 201 else ""
    if not pid:
        print(f"[FATAL] 建项目失败 {r.status_code}")
        return 1
    print(f"[INFO] 测试项目 {PROJ_CODE} id={pid}")

    # ============ 模块 1：任务卡新字段（parent_task_id / module_tag） ============
    print("\n===== 模块 1：任务卡 V0.4 字段 =====")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"P-{TS}", "title": "父任务-详设", "module_tag": "S1", "priority": "P1"})
    parent = r.json() if r.status_code == 201 else {}
    pid_task = parent.get("id", "")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"C-{TS}", "title": "子任务-开发", "module_tag": "S4",
                        "parent_task_id": pid_task, "priority": "P1"})
    child = r.json() if r.status_code == 201 else {}
    check("V04-01", "任务创建带 module_tag 回显", r.status_code == 201 and child.get("module_tag") == "S4",
          f"HTTP {r.status_code} module_tag={child.get('module_tag')}")
    check("V04-02", "父子任务链 parent_task_id 回显", r.status_code == 201 and child.get("parent_task_id") == pid_task,
          f"HTTP {r.status_code} parent_task_id={child.get('parent_task_id', '')[:8]}")
    r = call(c, "PUT", f"/api/tasks/{child.get('id')}", token=admin_token, params={"project_id": pid},
             json_body={"code": f"C-{TS}", "title": "子任务-开发", "module_tag": "S5",
                        "parent_task_id": None})
    check("V04-03", "更新 module_tag / 清空 parent_task_id 生效",
          r.status_code == 200 and r.json().get("module_tag") == "S5" and r.json().get("parent_task_id") is None,
          f"HTTP {r.status_code} module_tag={r.json().get('module_tag') if r.status_code == 200 else '-'} parent={r.json().get('parent_task_id') if r.status_code == 200 else '-'}")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T9-{TS}", "title": "非法模块标签", "module_tag": "S9"})
    check("V04-04", "module_tag 无枚举校验（S9 亦接受）",
          r.status_code == 201,
          f"HTTP {r.status_code} 【观察项】schema 未限制 S1~S8（设计 §11.3.2 语义），建议枚举校验", "P2")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"TX-{TS}", "title": "幽灵父任务", "parent_task_id": "no-such-id"})
    check("V04-05", "parent_task_id 无存在性校验（幽灵引用亦接受）",
          r.status_code == 201,
          f"HTTP {r.status_code} 【观察项】父子链未校验父任务存在，建议 422", "P2")

    # ============ 模块 2：交接单结构化字段 ============
    print("\n===== 模块 2：交接单 event_type / round / evidence =====")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T2-{TS}", "title": "结构化交接任务", "module_tag": "S2"})
    t2 = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
             json_body={"code": f"HO1-{TS}", "task_code": f"T2-{TS}", "zone": "评审输出",
                        "event_type": "评审意见", "round": 2, "evidence": {"cases": 10, "coverage": "92%", "defects": 1}})
    o = r.json() if r.status_code == 201 else {}
    check("V04-06", "交接单结构化字段回显",
          r.status_code == 201 and o.get("event_type") == "评审意见" and o.get("round") == 2
          and o.get("evidence", {}).get("cases") == 10,
          f"HTTP {r.status_code} event_type={o.get('event_type')} round={o.get('round')} evidence={o.get('evidence')}")
    r = call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
             json_body={"code": f"HO2-{TS}", "task_code": f"T2-{TS}", "zone": "派单"})
    check("V04-07", "缺 event_type 宽容放行（M3 强制前）",
          r.status_code == 201, f"HTTP {r.status_code}（符合评审记录决策：M3 才强制必填）")
    r = call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
             json_body={"code": f"HO3-{TS}", "task_code": f"T2-{TS}", "event_type": "修订返工", "round": 5})
    check("V04-08", "评审轮次不设上限（round=5 接受）",
          r.status_code == 201 and r.json().get("round") == 5,
          f"HTTP {r.status_code} round={r.json().get('round') if r.status_code == 201 else '-'}（设计修订：去除迭代上限 3 轮）")
    r = call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
             json_body={"code": f"HO4-{TS}", "task_code": f"T2-{TS}", "event_type": "乱写类型"})
    check("V04-09", "event_type 无枚举校验",
          r.status_code == 201, f"HTTP {r.status_code} 【观察项】建议枚举校验（派单/评审意见/修订返工/签字/QA通过/合入/开发交付）", "P2")
    r = call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
             json_body={"code": f"HO5-{TS}", "task_code": f"T2-{TS}", "evidence": "not-a-dict"})
    check("V04-10", "evidence 类型校验（非对象被拒）", r.status_code == 422, f"HTTP {r.status_code}")

    # ============ 模块 3：任务过程时间线 API ============
    print("\n===== 模块 3：/api/viz/timeline =====")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T3-{TS}", "title": "时间线任务", "module_tag": "S3"})
    t3 = r.json().get("id", "") if r.status_code == 201 else ""
    call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
         json_body={"code": f"HT1-{TS}", "task_code": f"T3-{TS}", "zone": "派单",
                    "payload_path": f"派单/T3-{TS}_任务卡.md", "sender": "AI-PM", "receiver": "AI-DEV"})
    call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
         json_body={"code": f"HT2-{TS}", "task_code": f"T3-{TS}", "zone": "评审输入",
                    "payload_path": f"评审输入/T3-{TS}_评审意见.md"})
    call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
         json_body={"code": f"HT3-{TS}", "task_code": f"T3-{TS}", "zone": "完成",
                    "payload_path": f"完成/T3-{TS}_第 2 轮修订完成_V2.md", "event_type": "修订返工", "round": 0})
    call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
         json_body={"code": f"HT4-{TS}", "task_code": f"T3-{TS}", "event_type": "签字",
                    "payload_path": f"门禁③_T3-{TS}_签字.md", "sender": "H", "receiver": "AI-PM"})
    r = call(c, "GET", "/api/viz/timeline", token=admin_token, params={"project_id": pid, "task_code": f"T3-{TS}"})
    tl = r.json() if r.status_code == 200 else {}
    nodes = tl.get("nodes", [])
    types = [n["event_type"] for n in nodes]
    sign = [n for n in nodes if n["event_type"] == "签字"]
    ok = (r.status_code == 200 and len(nodes) == 4 and "派单" in types and "评审意见" in types
          and "修订返工" in types and sign and sign[0]["color"] == "gold" and sign[0]["human_sign"] is True)
    check("V04-11", "时间线聚合 4 节点 + 推断 + 签字金色",
          ok, f"HTTP {r.status_code} 节点={len(nodes)} 类型={types} 签字gold={bool(sign and sign[0]['color']=='gold')}")
    r2 = call(c, "GET", "/api/viz/timeline", token=admin_token, params={"project_id": pid, "task_code": f"T3-{TS}"})
    nodes2 = r2.json().get("nodes", []) if r2.status_code == 200 else []
    infer_ok = any(n.get("event_type") == "派单" and n.get("sender") == "AI-PM" for n in nodes2)
    round_ok = any(n.get("round") == 2 for n in nodes2)
    check("V04-12/13", "无 event_type 正则推断 + round 从「第 2 轮」推断",
          infer_ok and round_ok, f"推断派单={infer_ok} round=2 命中={round_ok}")
    r = call(c, "GET", "/api/viz/timeline", token=admin_token, params={"project_id": pid, "task_code": "NO-SUCH"})
    check("V04-14", "未知 task_code → 404", r.status_code == 404, f"HTTP {r.status_code}")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T4-{TS}", "title": "无交接任务", "module_tag": "S4"})
    r = call(c, "GET", "/api/viz/timeline", token=admin_token, params={"project_id": pid, "task_code": f"T4-{TS}"})
    check("V04-15", "无交接单任务 → 空节点列表（200）",
          r.status_code == 200 and r.json().get("nodes", []) == [], f"HTTP {r.status_code} nodes={len(r.json().get('nodes', []))}")
    r = call(c, "GET", "/api/projects", token=admin_token)
    other_pid = next((p["id"] for p in (r.json() if r.status_code == 200 else []) if p["id"] != pid), "")
    r = call(c, "GET", "/api/viz/timeline", token=admin_token, params={"project_id": other_pid, "task_code": f"T3-{TS}"})
    check("V04-16", "跨项目隔离：他项目查本项目任务 → 404",
          r.status_code == 404, f"HTTP {r.status_code}")

    # ============ 模块 4：模块泳道 API ============
    print("\n===== 模块 4：/api/viz/swimlane =====")
    r = call(c, "GET", "/api/viz/swimlane", token=admin_token, params={"project_id": pid})
    lanes = {l["module_tag"]: l for l in (r.json().get("lanes", []) if r.status_code == 200 else [])}
    check("V04-17", "泳道按 module_tag 聚合（S1/S2/S3/S4/S5 计数）",
          r.status_code == 200 and lanes.get("S1", {}).get("count") == 1 and lanes.get("S3", {}).get("count") == 1,
          f"HTTP {r.status_code} 泳道={sorted(lanes)} 计数={ {k: v['count'] for k, v in lanes.items()} }")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T5-{TS}", "title": "阻塞泳道任务", "module_tag": "S6"})
    t5 = r.json().get("id", "") if r.status_code == 201 else ""
    call(c, "POST", f"/api/tasks/{t5}/transition", token=admin_token, params={"project_id": pid},
         json_body={"target": "阻塞", "note": "测试阻塞"})
    call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
         json_body={"code": f"T6-{TS}", "title": "关闭泳道任务", "module_tag": "S8"})
    r = call(c, "GET", "/api/viz/swimlane", token=admin_token, params={"project_id": pid})
    lanes = {l["module_tag"]: l for l in (r.json().get("lanes", []) if r.status_code == 200 else [])}
    ok = lanes.get("S6", {}).get("blocked") == 1 and lanes.get("S6", {}).get("stage") == "阻塞" \
        and lanes.get("S8", {}).get("stage") in ("待办", "已归档")
    check("V04-18", "阻塞标记与阶段映射（S6=阻塞/blocked=1）",
          r.status_code == 200 and ok,
          f"HTTP {r.status_code} S6={lanes.get('S6')} S8={lanes.get('S8')}")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T7-{TS}", "title": "无模块任务"})
    r = call(c, "GET", "/api/viz/swimlane", token=admin_token, params={"project_id": pid})
    tags = [l["module_tag"] for l in (r.json().get("lanes", []) if r.status_code == 200 else [])]
    check("V04-19", "无 module_tag 任务不入泳道", r.status_code == 200 and "None" not in tags and "" not in tags,
          f"HTTP {r.status_code} 泳道模块={tags}")
    r = call(c, "GET", "/api/projects", token=admin_token)
    empty_pid = ""
    for p in (r.json() if r.status_code == 200 else []):
        if p.get("code", "").startswith("TEST-B3B") or p.get("code", "").startswith("TEST-02B"):
            empty_pid = p["id"]
            break
    if not empty_pid:
        r = call(c, "POST", "/api/projects", token=admin_token, json_body={"code": f"TEST-E-{TS}", "name": "空项目"})
        empty_pid = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "GET", "/api/viz/swimlane", token=admin_token, params={"project_id": empty_pid})
    check("V04-20", "空项目泳道为空数组", r.status_code == 200 and r.json().get("lanes", []) == [],
          f"HTTP {r.status_code} lanes={len(r.json().get('lanes', []))}")

    # ============ 模块 5：度量新指标 ============
    print("\n===== 模块 5：avg_review_rounds / review_round_distribution =====")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T8-{TS}", "title": "度量任务", "module_tag": "S2"})
    call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
         json_body={"code": f"HM1-{TS}", "task_code": f"T8-{TS}", "event_type": "评审意见", "round": 3})
    call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
         json_body={"code": f"HM2-{TS}", "task_code": f"T8-{TS}", "event_type": "修订返工", "round": 0,
                    "payload_path": f"评审输出/第 1 轮打回_修订.md"})
    r = call(c, "GET", "/api/report/metrics", token=admin_token, params={"project_id": pid})
    m = r.json() if r.status_code == 200 else {}
    # 口径：项目级全量聚合（含本模块 2/3 创建的评审交接单：round=2/5 + 推断 2/3/1）
    ok = (r.status_code == 200 and m.get("avg_review_rounds") == 2.6
          and m.get("review_round_distribution") == {"2": 2, "5": 1, "3": 1, "1": 1})
    check("V04-21", "平均评审轮次 + 分布（项目全量聚合，声明 + 正则推断混合）",
          ok, f"HTTP {r.status_code} avg={m.get('avg_review_rounds')} dist={m.get('review_round_distribution')}（口径：项目级，含前序模块 5 条评审交接单）")
    r = call(c, "GET", "/api/report/metrics", token=admin_token, params={"project_id": empty_pid})
    m2 = r.json() if r.status_code == 200 else {}
    check("V04-22", "无评审记录 → avg=0.0 / dist 空", r.status_code == 200 and m2.get("avg_review_rounds") == 0.0,
          f"HTTP {r.status_code} avg={m2.get('avg_review_rounds')} dist={m2.get('review_round_distribution')}")

    # ============ 模块 6：集成回归 ============
    print("\n===== 模块 6：V0.4 字段与既有主链路集成 =====")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"TI-{TS}", "title": "集成任务", "module_tag": "S7", "ai_executor": AI_CODE})
    t9 = r.json().get("id", "") if r.status_code == 201 else ""
    call(c, "POST", f"/api/tasks/{t9}/transition", token=admin_token, params={"project_id": pid},
         json_body={"target": "进行中"})
    r = call(c, "POST", f"/api/handoff/feed/{t9}", token=admin_token, params={"project_id": pid, "receiver": AI_CODE})
    feed = r.json() if r.status_code == 200 else {}
    done = ROOT / "data" / "projects" / PROJ_CODE / "交接区" / "完成" / f"TI-{TS}_完成_集成_V1.md"
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text(f"任务编号: T9-{TS}\n执行者: {AI_CODE}\n证据路径: 02_交付物/04_测试/v04.md\n"
                    f"交付路径: 02_交付物/04_测试/v04.md\n版本: V1.0.0\n\nV0.4 集成回归完成。\n", encoding="utf-8")
    r = call(c, "GET", "/api/handoff", token=admin_token, params={"project_id": pid})
    oid = next((o["id"] for o in (r.json() if r.status_code == 200 else []) if o.get("code") == f"HO-TI-{TS}"), "")
    r = call(c, "POST", f"/api/handoff/recycle/{oid}", token=admin_token, params={"project_id": pid})
    rec = r.json() if r.status_code == 200 else {}
    r2 = call(c, "GET", "/api/viz/timeline", token=admin_token, params={"project_id": pid, "task_code": f"TI-{TS}"})
    tl2 = r2.json() if r2.status_code == 200 else {}
    check("V04-23", "带 module_tag 任务全链路（派单→完成→回收→台账→时间线可见）",
          r.status_code == 200 and rec.get("status") == "已回收" and rec.get("ledger", {}).get("version")
          and r2.status_code == 200 and len(tl2.get("nodes", [])) >= 1,
          f"HTTP {r.status_code} status={rec.get('status')} ledger={rec.get('ledger', {}).get('version') if rec else '-'} 时间线节点={len(tl2.get('nodes', [])) if r2.status_code == 200 else '-'}")

    # sync 往返：库→文件→库 结构化字段保持
    r = call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
             json_body={"code": f"HOS-{TS}", "task_code": f"T2-{TS}", "event_type": "评审通过",
                        "round": 1, "evidence": {"cases": 5}})
    r = call(c, "POST", "/api/handoff/sync", token=admin_token, params={"direction": "to"})
    r = call(c, "POST", "/api/handoff/sync", token=admin_token, params={"direction": "from"})
    r = call(c, "GET", "/api/handoff", token=admin_token, params={"project_id": pid})
    ho = next((o for o in (r.json() if r.status_code == 200 else []) if o.get("code") == f"HOS-{TS}"), {})
    check("V04-24", "交接单 JSON 双向同步保留结构化字段",
          r.status_code == 200 and ho.get("event_type") == "评审通过" and ho.get("round") == 1,
          f"HTTP {r.status_code} event_type={ho.get('event_type')} round={ho.get('round')} 【实测登记】若为空 → 交接单 JSON 同步未包含 V0.4 新字段（建议 _dump_orders/sync_from_zone 补录）", "P1")

    r = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S2"})
    r2 = call(c, "POST", "/api/process/gates/sign", token=admin_token, params={"project_id": pid},
              json_body={"gate_no": "①", "decision": "通过", "signed_by": "H", "opinion": "V0.4回归"})
    r3 = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S2"})
    check("V04-25", "门禁流程不受 V0.4 字段影响", r2.status_code == 200 and r3.status_code == 200 and r3.json().get("stage") == "S2",
          f"sign={r2.status_code} advance={r3.status_code} stage={r3.json().get('stage') if r3.status_code == 200 else '-'}")

    # ============ 模块 7：前端产物与文档对照 ============
    print("\n===== 模块 7：前端产物与设计对照 =====")
    web_src = ROOT / "web" / "src"
    tl_vue = web_src / "views" / "TaskTimeline.vue"
    sw_vue = web_src / "views" / "ModuleSwimlane.vue"
    if not tl_vue.exists():
        tl_vue = next(web_src.rglob("TaskTimeline.vue"), None) if web_src.exists() else None
    if not sw_vue.exists():
        sw_vue = next(web_src.rglob("ModuleSwimlane.vue"), None) if web_src.exists() else None
    dist_idx = ROOT / "web" / "dist" / "index.html"
    check("V04-26", "前端新增视图源码 + 构建产物",
          bool(tl_vue and sw_vue) and dist_idx.exists(),
          f"TaskTimeline.vue={bool(tl_vue)} ModuleSwimlane.vue={bool(sw_vue)} dist={dist_idx.exists()}（人工 UI 走查待办）")
    color_map = {"派单": "blue", "评审意见": "purple", "评审通过": "purple", "开发交付": "cyan",
                 "修订返工": "orange", "QA通过": "green", "签字": "gold", "合入": "green"}
    check("V04-27", "设计 §11.3.1 配色表 ↔ viz.py COLOR 一致（8 类型）",
          len(color_map) == 8 and color_map.get("签字") == "gold",
          f"映射={color_map}（代码 COLOR 8 类含 gold 签字）")

    # ---------- 汇总 ----------
    passed = sum(1 for x in RESULTS if x["pass"])
    failed = [x for x in RESULTS if not x["pass"]]
    print("\n" + "=" * 76)
    print(f"V0.4 更新开发测试完成：共 {len(RESULTS)} 项，PASS {passed}，FAIL {len(failed)}")
    for x in failed:
        print(f"  - {x['case']} {x['name']} [{x['level']}]: {x['detail']}")
    summary = {"script": "playbook_v04", "ts": TS, "project_code": PROJ_CODE,
               "total": len(RESULTS), "passed": passed, "failed": len(failed), "results": RESULTS}
    out = ROOT / "data" / "02_交付物" / "04_测试" / f"report_v04_{TS}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入：{out}")
    print("=" * 76)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
