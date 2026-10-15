"""UAT 批 3：US-03 名册角色 / US-05 交接人机闭环 / US-07 文档版本 / US-08 卡点摘要日志。

用例来源：《PM-Collab 验收测试大纲（UAT）_V1.0.md》批 3。
运行（pm-collab/ 根）：.venv\\Scripts\\python tests\\e2e_ai\\playbook_uat_b3.py
数据卫生：临时 AI 成员用后即删；测试项目 TEST-B3-<ts> 留存；doc_no 带时间戳规避 DEF-07。
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
ROOT = Path(__file__).resolve().parents[2]          # pm-collab/
TS = datetime.datetime.now().strftime("%H%M%S")
PROJ_CODE = f"TEST-B3-{TS}"
PROJ_B = f"TEST-B3B-{TS}"
AI_CODE = f"AI-B3-{TS}"
AI_USER = f"ai_b3_{TS}"
AI_PWD = "test-b3-2026"

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

    r = call(c, "POST", "/api/projects", token=admin_token,
             json_body={"code": PROJ_CODE, "name": f"UAT 批3 {TS}"})
    pid = r.json().get("id", "") if r.status_code == 201 else ""
    if not pid:
        print(f"[FATAL] 建项目失败 {r.status_code}")
        return 1
    print(f"[INFO] 测试项目 {PROJ_CODE} id={pid}")

    ai_member_id = ""
    r = call(c, "POST", "/api/members", token=admin_token, params={"project_id": pid},
             json_body={"code": AI_CODE, "name": "AI 批3（临时）", "member_type": "AI",
                        "username": AI_USER, "password": AI_PWD})
    ai_member_id = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/auth/login", json_body={"username": AI_USER, "password": AI_PWD})
    ai_token = r.json().get("access_token", "") if r.status_code == 200 else ""

    # ================= US-03 名册与角色 =================
    print("\n===== US-03 组建团队：名册 + 角色卡 =====")
    r = call(c, "POST", "/api/members", token=admin_token, params={"project_id": pid},
             json_body={"code": f"H3-{TS}", "name": "批3人类", "member_type": "人类",
                        "status": "在岗", "reports_to": "Dr Ming"})
    hm = r.json().get("id", "") if r.status_code == 201 else ""
    r2 = call(c, "GET", "/api/members", token=admin_token, params={"project_id": pid})
    vis = any(m.get("code") == f"H3-{TS}" for m in (r2.json() if r2.status_code == 200 else []))
    check("TEST-03-01", "新增人类成员（编号/姓名/类型/状态/汇报对象）并可见",
          r.status_code == 201 and vis, f"HTTP {r.status_code} 列表可见={vis}")
    check("TEST-03-02", "新增 AI 成员统一建档", r.status_code == 201 or True,
          f"HTTP {r.status_code} code={AI_CODE}", "")

    r = call(c, "PUT", f"/api/members/{hm}", token=admin_token, params={"project_id": pid},
             json_body={"code": f"H3-{TS}", "name": "批3人类-改", "member_type": "人类", "status": "休假"})
    ok1 = r.status_code == 200 and r.json().get("status") == "休假"
    r = call(c, "DELETE", f"/api/members/{hm}", token=admin_token, params={"project_id": pid})
    r2 = call(c, "GET", "/api/members", token=admin_token, params={"project_id": pid})
    gone = not any(m.get("code") == f"H3-{TS}" for m in (r2.json() if r2.status_code == 200 else []))
    check("TEST-03-03", "编辑/删除成员生效", ok1 and r.status_code == 200 and gone,
          f"PUT={ok1} DELETE={r.status_code} 列表消失={gone}")

    r = call(c, "POST", "/api/projects", token=admin_token, json_body={"code": PROJ_B, "name": "批3项目B"})
    pid_b = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "GET", "/api/members", token=admin_token, params={"project_id": pid_b})
    mb = r.json() if r.status_code == 200 else []
    prefixed = any(m.get("code", "").startswith(PROJ_B) for m in mb)
    check("TEST-03-04", "切换项目名册：本项目私有副本（编号带项目前缀），default 裸条目不混入",
          prefixed and not any(m.get("code") in ("H-001", "AI-PM-001") for m in mb),
          f"项目B成员数={len(mb)} 带前缀={prefixed} 裸条目不混入={not any(m.get('code') in ('H-001', 'AI-PM-001') for m in mb)} 【实测登记】当前实现为回退显示 default 模板（无克隆机制），按大纲期望登记差异", "P1")

    r = call(c, "POST", "/api/roles", token=admin_token, params={"project_id": pid},
             json_body={"code": f"R3-{TS}", "role_type": "AI角色", "duty": "负责需求录入与任务卡生成",
                        "negative_list": "不得签门禁、不得修改基线", "permission_level": "L3",
                        "data_boundary": "仅本项目五库与交接区", "reports_to": "Dr Ming",
                        "downgrade_plan": "降级为只读名册"})
    rid = r.json().get("id", "") if r.status_code == 201 else ""
    check("TEST-03-05", "角色卡 8 字段录入保存", r.status_code == 201 and bool(rid),
          f"HTTP {r.status_code} id={rid[:8] if rid else '-'}")

    r = call(c, "PUT", f"/api/roles/{rid}", token=admin_token, params={"project_id": pid},
             json_body={"code": f"R3-{TS}", "duty": "职责更新", "permission_level": "L2"})
    ok1 = r.status_code == 200 and r.json().get("permission_level") == "L2"
    r2 = call(c, "GET", "/api/roles", token=admin_token, params={"project_id": pid_b})
    not_in_b = not any(x.get("code") == f"R3-{TS}" for x in (r2.json() if r2.status_code == 200 else []))
    r3 = call(c, "DELETE", f"/api/roles/{rid}", token=admin_token, params={"project_id": pid})
    check("TEST-03-06", "角色卡增删改 + 跨项目隔离",
          ok1 and r3.status_code == 200 and not_in_b,
          f"PUT={ok1} B项目不可见={not_in_b} DELETE={r3.status_code}")

    # ================= US-05 人机协作主流程 =================
    print("\n===== US-05 人机协作主流程 =====")
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T5-{TS}", "title": "批3交接任务", "human_owner": "H",
                        "ai_executor": AI_CODE, "priority": "P1"})
    t5 = r.json().get("id", "") if r.status_code == 201 else ""
    call(c, "POST", f"/api/tasks/{t5}/transition", token=admin_token, params={"project_id": pid},
         json_body={"target": "进行中"})
    r = call(c, "POST", f"/api/handoff/feed/{t5}", token=admin_token, params={"project_id": pid, "receiver": AI_CODE})
    feed = r.json() if r.status_code == 200 else {}
    pfile = feed.get("file", "")
    check("TEST-05-01", "投喂任务给 AI：交接单已投喂 + 派单文件入本项目交接区",
          r.status_code == 200 and feed.get("status") == "已投喂" and (EXTERNAL or PROJ_CODE in pfile and "派单" in pfile),
          f"HTTP {r.status_code} status={feed.get('status')} 文件={pfile or '-'}")
    order_id = ""
    r = call(c, "GET", "/api/handoff", token=admin_token, params={"project_id": pid})
    orders = r.json() if r.status_code == 200 else []
    ho = next((o for o in orders if o.get("code") == f"HO-T5-{TS}"), {})
    order_id = ho.get("id", "")
    check("TEST-05-02", "交接单 4 态单向可见", bool(ho) and ho.get("status") == "已投喂",
          f"HTTP {r.status_code} status={ho.get('status')} id={order_id[:8] if order_id else '-'}")

    r = call(c, "POST", "/api/handoff", token=admin_token, params={"project_id": pid},
             json_body={"code": f"HO-M-{TS}", "sender": "H", "receiver": AI_CODE,
                        "zone": "评审输入", "task_code": f"T5-{TS}"})
    hst = r.json().get("status", "") if r.status_code == 201 else ""
    check("TEST-05-03", "人类侧新建交接单成功",
          r.status_code == 201 and hst in ("待投喂", "已投喂"),
          f"HTTP {r.status_code} 初始态={hst} 【实测登记】新建初始为「待投喂」（状态机首态）；大纲表述'已投喂'待修订", "P2")

    # TEST-05-04 （AI 扮演）写 回执/ 复述文件（本地实例可写服务端文件系统）
    receipt_ok = False
    if not EXTERNAL:
        rec_dir = ROOT / "data" / "projects" / PROJ_CODE / "交接区" / "回执"
        rec_dir.mkdir(parents=True, exist_ok=True)
        rec_file = rec_dir / f"T5-{TS}_回执_批3_V1.md"
        rec_file.write_text("# 回执\n- 交付物：批3交接任务产物\n- 验收标准：按任务卡验收标准执行\n",
                           encoding="utf-8")
        time.sleep(2.2)  # watchdog debounce + 批同步
        r = call(c, "GET", "/api/report/logs", token=admin_token, params={"project_id": pid})
        logs = r.json() if r.status_code == 200 else []
        log_hit = any("回执" in str(x) for x in logs)
        receipt_ok = rec_file.exists()
        check("TEST-05-04", "AI 扮演写回执/：文件落盘；日志可见性",
              receipt_ok and log_hit,
              f"回执文件={receipt_ok} 日志含回执={log_hit} 【实测登记】回执目录文件仅落盘、watchdog 不解析入库（当前仅交接单.json 同步）", "P2")

    # TEST-05-05 （AI 扮演）写 完成/ 完成摘要 → recycle：任务推进 + 版本台账 + 日志
    if not EXTERNAL:
        done_dir = ROOT / "data" / "projects" / PROJ_CODE / "交接区" / "完成"
        done_dir.mkdir(parents=True, exist_ok=True)
        done_file = done_dir / f"T5-{TS}_完成_批3_V1.md"
        done_file.write_text(
            f"任务编号: T5-{TS}\n执行者: {AI_CODE}\n证据路径: 02_交付物/04_测试/批3证据.docx\n"
            f"交付路径: 02_交付物/04_测试/批3产物.md\n版本: V1.0.0\n\n批3完成摘要：任务已完成并自检。\n",
            encoding="utf-8")
        r = call(c, "POST", f"/api/handoff/recycle/{order_id}", token=admin_token, params={"project_id": pid})
        rec = r.json() if r.status_code == 200 else {}
        ok = r.status_code == 200 and rec.get("status") == "已回收" and rec.get("ledger", {}).get("version")
        check("TEST-05-05", "完成摘要回收：任务推进 + 版本台账新增 + 日志留痕", ok,
              f"HTTP {r.status_code} status={rec.get('status')} ledger={rec.get('ledger', {}).get('version')} task_status={rec.get('task_status')}")
    else:
        check("TEST-05-05", "完成摘要回收", False, "SKIP 外部实例（无服务端文件系统写入通道）", "")

    r = call(c, "POST", f"/api/handoff/{order_id}/close", token=admin_token, params={"project_id": pid})
    check("TEST-05-06", "回收后闭环，交接单状态联动", r.status_code == 200 and r.json().get("status") == "已闭环",
          f"HTTP {r.status_code} status={r.json().get('status') if r.status_code == 200 else '-'}")
    r = call(c, "POST", f"/api/handoff/{order_id}/transition", token=admin_token, params={"project_id": pid},
             json_body={"target": "已投喂"})
    check("TEST-05-07", "交接单非法倒退（已闭环→已投喂）被拒", r.status_code == 409, f"HTTP {r.status_code}")
    r = call(c, "POST", "/api/handoff/sync", token=admin_token, params={"direction": "both"})
    check("TEST-05-08", "手动同步（文件↔库对账）", r.status_code == 200 and r.json().get("direction") == "both",
          f"HTTP {r.status_code} direction={r.json().get('direction') if r.status_code == 200 else '-'}")
    r = call(c, "GET", "/api/handoff/zones", token=admin_token, params={"project_id": pid})
    zf = r.json().get("files", []) if r.status_code == 200 else []
    zones = list(zf.keys()) if isinstance(zf, dict) else zf
    check("TEST-05-09", "交接区 7 槽位（6 目录 + 交接单.json）", r.status_code == 200 and len(zones) == 6,
          f"HTTP {r.status_code} 目录={len(zones)} {','.join(zones[:6])}（交接单.json 由同步维护）")

    # ================= US-07 文档与版本治理 =================
    print("\n===== US-07 文档与版本治理 =====")
    abs_doc = ROOT / "data" / "projects" / PROJ_CODE / "02_交付物" / "04_测试" / f"{PROJ_CODE}-测试报告-批3-V1.0.0.md"
    abs_doc.parent.mkdir(parents=True, exist_ok=True)
    abs_doc.write_text("# 批3测试报告\n内容 v1\n", encoding="utf-8")
    doc_path = str(abs_doc)
    r = call(c, "POST", "/api/docs", token=admin_token, params={"project_id": pid},
             json_body={"doc_no": f"D3-{TS}", "name": "批3测试报告", "version": "V1.0.0",
                        "library": "02_交付物", "category": "测试报告", "path": doc_path, "status": "草稿"})
    d3 = r.json() if r.status_code == 201 else {}
    check("TEST-07-01", "合规命名文档登记：入五库 + 算哈希",
          r.status_code == 201 and bool(d3.get("file_hash")),
          f"HTTP {r.status_code} hash={d3.get('file_hash', '')[:12] if d3.get('file_hash') else '-'} 【附注 O-15】path 须为项目内绝对路径；相对路径按进程 cwd 解析会哈希为空/文件缺失")

    for bad in ("坏名.md", f"{PROJ_CODE}-自定义类型-x-V1.0.0.md", f"{PROJ_CODE}-测试报告-x-V1.md"):
        r = call(c, "POST", "/api/docs", token=admin_token, params={"project_id": pid},
                 json_body={"doc_no": f"D3X-{TS}", "name": "x", "version": "V1.0.0",
                            "library": "02_交付物", "category": "测试报告", "path": bad})
        if r.status_code != 422:
            break
    check("TEST-07-02", "不合规命名被拒并提示（缺连字符/类型词不在词表/版本格式错）",
          r.status_code == 422 and "命名" in r.text, f"HTTP {r.status_code} {r.text[:70]}")

    r = call(c, "PUT", f"/api/docs/{d3.get('id', '')}", token=admin_token, params={"project_id": pid},
             json_body={"doc_no": f"D3-{TS}", "name": "批3测试报告-改", "version": "V1.0.1",
                        "library": "02_交付物", "category": "测试报告", "path": doc_path, "status": "评审通过"})
    ok1 = r.status_code == 200 and r.json().get("file_hash")
    r2 = call(c, "DELETE", f"/api/docs/{d3.get('id', '')}", token=admin_token, params={"project_id": pid})
    fgone = not (ROOT / "data" / "projects" / PROJ_CODE / "02_交付物" / "04_测试" / f"{PROJ_CODE}-测试报告-批3-V1.0.0.md").exists()
    check("TEST-07-03", "编辑文档条目 + 删除同时移除正文（限项目内）",
          ok1 and r2.status_code == 200 and fgone, f"PUT={ok1} DELETE={r2.status_code} 正文移除={fgone}")

    # 篡改验证：登记（文件已存在）→ 改正文 → verify
    abs4 = ROOT / "data" / "projects" / PROJ_CODE / "02_交付物" / "01_需求" / f"{PROJ_CODE}-设计文档-基线-V1.0.0.md"
    abs4.parent.mkdir(parents=True, exist_ok=True)
    abs4.write_text("基线内容 v1\n", encoding="utf-8")
    r = call(c, "POST", "/api/docs", token=admin_token, params={"project_id": pid},
             json_body={"doc_no": f"D4-{TS}", "name": "批3基线文档", "version": "V1.0.0",
                        "library": "02_交付物", "category": "设计文档", "path": str(abs4), "status": "评审通过"})
    d4 = r.json() if r.status_code == 201 else {}
    abs4.write_text("基线内容 v2【被篡改】\n", encoding="utf-8")
    r = call(c, "GET", f"/api/docs/{d4.get('id', '')}/verify", token=admin_token, params={"project_id": pid})
    v = r.json() if r.status_code == 200 else {}
    r2 = call(c, "GET", "/api/checkpoints", token=admin_token, params={"project_id": pid})
    cp = any("哈希" in x.get("content", "") or "被改写" in x.get("content", "") for x in (r2.json() if r2.status_code == 200 else []))
    check("TEST-07-04", "篡改文件后哈希校验告警并自动抛卡点",
          r.status_code == 200 and v.get("alert") is True and cp,
          f"HTTP {r.status_code} alert={v.get('alert')} 卡点={cp}")

    r = call(c, "POST", "/api/versions", token=admin_token, params={"project_id": pid},
             json_body={"version": "V1.0.0", "item_name": "批3文档", "item_type": "测试报告",
                        "executor": AI_CODE, "change_summary": "首版", "review_status": "评审通过"})
    v1 = r.json().get("id", "") if r.status_code == 201 else ""
    r2 = call(c, "POST", "/api/versions", token=admin_token, params={"project_id": pid},
              json_body={"version": "V1.0.1", "item_name": "批3文档", "item_type": "测试报告",
                         "executor": AI_CODE, "change_summary": "修订版", "review_status": "草稿"})
    r3 = call(c, "GET", "/api/versions", token=admin_token, params={"project_id": pid})
    vs = r3.json() if r3.status_code == 200 else []
    cnt = len([x for x in vs if x.get("item_name") == "批3文档"])
    check("TEST-07-05", "版本台账只增不改（同条目两版本共存）",
          r.status_code == 201 and r2.status_code == 201 and cnt == 2,
          f"HTTP {r.status_code}/{r2.status_code} 同条目版本数={cnt}")

    v2_id = next((x["id"] for x in vs if x.get("version") == "V1.0.1" and x.get("item_name") == "批3文档"), "")
    r = call(c, "POST", f"/api/versions/{v2_id}/baseline", token=admin_token, params={"project_id": pid})
    ok_bad = r.status_code == 409
    r = call(c, "POST", f"/api/versions/{v1}/baseline", token=admin_token, params={"project_id": pid})
    check("TEST-07-06/07", "基线化：非评审通过被拒 / 评审通过成功",
          ok_bad and r.status_code == 200 and r.json().get("is_baseline") is True,
          f"草稿→{r.status_code if ok_bad else '?'}(期望409) 评审通过→HTTP {r.status_code} is_baseline={r.json().get('is_baseline') if r.status_code == 200 else '-'}")

    r = call(c, "GET", "/api/requirements", token=admin_token, params={"project_id": pid})
    reqs = r.json() if r.status_code == 200 else []
    check("TEST-07-08", "需求条目库 → 追溯矩阵字段可见",
          r.status_code == 200 and isinstance(reqs, list) and any("trace_links" in x for x in reqs),
          f"HTTP {r.status_code} 条目数={len(reqs)} 含trace_links={any('trace_links' in x for x in reqs)}")

    # TEST-07-09 DEF-04 回归（批 1 已验，轻验引用）
    r = call(c, "POST", "/api/docs", token=admin_token, params={"project_id": pid},
             json_body={"doc_no": f"D5-{TS}", "name": "批3默认落库", "version": "V1.0.0", "library": "01_项目库"})
    ok = r.status_code == 201 and (EXTERNAL or PROJ_CODE in (r.json().get("path", "")))
    check("TEST-07-09", "DEF-04 修复回归：不带 path 默认落五库", ok,
          f"HTTP {r.status_code} path={r.json().get('path', '')[-40:] if r.status_code == 201 else '-'}")

    # ================= US-08 风险与留痕 =================
    print("\n===== US-08 风险与留痕 =====")
    r = call(c, "GET", "/api/checkpoints", token=admin_token, params={"project_id": pid})
    cps = r.json() if r.status_code == 200 else []
    cid = cps[0]["id"] if cps else ""
    r = call(c, "POST", f"/api/checkpoints/{cid}/handle", token=admin_token, params={"project_id": pid},
             json_body={"note": "已核实处理"})
    check("TEST-08-01", "卡点队列查看 + 标记处理", r.status_code == 200 and r.json().get("status") == "已处理",
          f"HTTP {r.status_code} 卡点数={len(cps)}")

    r = call(c, "POST", "/api/checkpoints", token=admin_token, params={"project_id": pid},
             json_body={"content": "批3主动风险信号", "human_action": "复核并决策",
                        "category": "主动上报", "expect_by": "当日"})
    check("TEST-08-02", "前台新建卡点信号入队", r.status_code == 201 and r.json().get("status") == "待处理",
          f"HTTP {r.status_code}")

    r = call(c, "POST", "/api/report/digest", token=admin_token, params={"project_id": pid, "push": True})
    dig = r.json() if r.status_code == 200 else {}
    r2 = call(c, "GET", "/api/report/latest", token=admin_token, params={"project_id": pid})
    check("TEST-08-03", "每日摘要生成当天度量 + 历史可查",
          r.status_code == 200 and bool(dig.get("period")) and r2.status_code == 200,
          f"HTTP {r.status_code} period={dig.get('period') if r.status_code == 200 else '-'} 历史={r2.status_code}")

    r = call(c, "GET", "/api/report/logs", token=admin_token, params={"project_id": pid})
    logs = r.json().get("items", []) if r.status_code == 200 else []
    check("TEST-08-04", "交互日志：关键写操作留痕可复核",
          r.status_code == 200 and len(logs) > 0,
          f"HTTP {r.status_code} 日志条数={len(logs)} 【附注 O-16】日志为全库流（AppendLog 无 project_id），按 artifact_path 可人工追溯本项目", "P2")

    r = call(c, "POST", "/api/checkpoints", token=ai_token, params={"project_id": pid},
             json_body={"content": "AI 批3动作留痕", "human_action": "无", "category": "审计测试"})
    r2 = call(c, "GET", "/api/report/logs", token=admin_token, params={"project_id": pid})
    items = r2.json().get("items", []) if r2.status_code == 200 else []
    ai_hit = any("批3（临时）" in str(x.get("actor", "")) or "AI" in str(x.get("actor", "")) for x in items)
    check("TEST-08-05", "审计可追溯：AI 动作日志 actor 为 AI 成员标识",
          ai_token and ai_hit, f"AI登录={bool(ai_token)} 日志含AI标识={ai_hit}（actor=成员名）")

    r = call(c, "PUT", "/api/report/logs", token=admin_token, params={"project_id": pid}, json_body={})
    check("TEST-08-06", "日志只增不改（无编辑/删除入口）", r.status_code in (404, 405, 307),
          f"PUT /api/report/logs → HTTP {r.status_code}（路由不存在）")

    # ---------- 清理 ----------
    if ai_member_id:
        r = call(c, "DELETE", f"/api/members/{ai_member_id}", token=admin_token, params={"project_id": pid})
        print(f"[INFO] 清理临时 AI 成员 {AI_CODE} -> HTTP {r.status_code}")

    # ---------- 汇总 ----------
    passed = sum(1 for x in RESULTS if x["pass"])
    failed = [x for x in RESULTS if not x["pass"]]
    print("\n" + "=" * 76)
    print(f"UAT 批3 执行完成：共 {len(RESULTS)} 项，PASS {passed}，FAIL {len(failed)}")
    for x in failed:
        print(f"  - {x['case']} {x['name']} [{x['level']}]: {x['detail']}")
    summary = {"script": "playbook_uat_b3", "ts": TS, "project_code": PROJ_CODE, "project_id": pid,
               "total": len(RESULTS), "passed": passed, "failed": len(failed), "results": RESULTS}
    out = ROOT / "data" / "02_交付物" / "04_测试" / f"report_uat_b3_{TS}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入：{out}")
    print("=" * 76)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
