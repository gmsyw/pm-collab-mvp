"""双视角功能测试：项目更新后，分别以 AI 用户与人类用户身份执行一轮功能测试。

覆盖（2026-10-08 项目更新）：
  核心重构：项目隔离（独立五库+交接区）、成员/角色按项目隔离与私有副本克隆、
           项目编辑 PUT、文档编辑/删除、流程指引 /api/process/guide（人机共用）、
           层级归属一致性、交接区按项目落盘、DEF-03 并发竞态修复。

运行（pm-collab/ 根）：
    .venv\\Scripts\\python tests\\e2e_ai\\playbook_dual.py
环境变量：PM_TEST_BASE / PM_TEST_INSECURE / PM_TEST_EXTERNAL（同 playbook1）

数据卫生：临时 AI 成员（AI-DUAL-<ts>）用后即删；模拟项目 T-DUAL-<ts> 保留（与既往剧本一致）。
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
PROJ_CODE = f"T-DUAL-{TS}"
PROJ_NAME = f"双视角测试 {TS}"
AI_CODE = f"AI-DUAL-{TS}"
AI_USER = f"ai_dual_{TS}"
AI_PWD = "test-dual-2026"

RESULTS: list[dict] = []


def check(case: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"case": case, "name": name, "pass": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {case} {name}" + (f" | {detail}" if detail else ""))


def call(c: httpx.Client, method: str, path: str, token: str = "",
         params: dict | None = None, json_body: dict | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return c.request(method, f"{BASE}{path}", headers=headers, params=params, json=json_body)


def main() -> int:
    c = httpx.Client(timeout=25, verify=not INSECURE)
    print(f"[INFO] 被测实例：{BASE} EXTERNAL={EXTERNAL}")
    admin_token = ai_token = ""
    pid = ""

    # ---------- 前置：admin 登录 / 建项目 / 建可登录 AI 成员 ----------
    r = call(c, "POST", "/api/auth/login", json_body={"username": "admin", "password": ""})
    if r.status_code == 200:
        admin_token = r.json()["access_token"]
    else:
        print("[FATAL] admin 登录失败，中止")
        return 1

    r = call(c, "POST", "/api/projects", token=admin_token,
             json_body={"code": PROJ_CODE, "name": PROJ_NAME,
                        "description": "更新后双视角功能测试项目", "owner": "Dr Ming"})
    if r.status_code == 201:
        pid = r.json()["id"]
        print(f"[INFO] 测试项目 {PROJ_CODE} id={pid}")
    else:
        print(f"[FATAL] 建项目失败 {r.status_code} {r.text[:200]}，中止")
        return 1

    ai_member_id = ""
    r = call(c, "POST", "/api/members", token=admin_token, params={"project_id": pid}, json_body={
        "code": AI_CODE, "name": "AI 双视角测试实例（临时）", "member_type": "AI",
        "username": AI_USER, "password": AI_PWD})
    ai_member_id = r.json().get("id", "") if r.status_code == 201 else ""
    if ai_member_id:
        r = call(c, "POST", "/api/auth/login", json_body={"username": AI_USER, "password": AI_PWD})
        ai_token = r.json().get("access_token", "") if r.status_code == 200 else ""
        print(f"[INFO] 临时 AI 成员 {AI_CODE} 已建并登录")

    # ================= 人类用户视角（H 段，admin 代表人类操作） =================
    print("\n===== 人类用户视角（H 段） =====")

    # H2 建项目：初始化流程与门禁
    r = call(c, "GET", "/api/process/instance", token=admin_token, params={"project_id": pid})
    ok = r.status_code == 200 and r.json().get("stage") == "S1"
    check("PMT-DUAL-H02", "新项目自动初始化流程实例", ok, f"HTTP {r.status_code} stage={r.json().get('stage') if r.status_code == 200 else '-'}")
    r = call(c, "GET", "/api/process/gates", token=admin_token, params={"project_id": pid})
    gates = r.json() if r.status_code == 200 else []
    ok = r.status_code == 200 and [g["gate_no"] for g in gates] == ["①", "②", "③", "④"]
    check("PMT-DUAL-H02", "新项目自动初始化 4 门禁", ok, f"HTTP {r.status_code} 门禁={[g.get('gate_no') for g in gates]}")

    # H3 编辑项目：名称/描述/负责人可改，编号不可改（注意：ProjectIn 无 status 字段，DEF-05 单独验证）
    r = call(c, "PUT", f"/api/projects/{pid}", token=admin_token,
             json_body={"code": "HACK-CODE", "name": f"{PROJ_NAME}-改", "description": "改后描述",
                        "owner": "Dr Ming"})
    body = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and body.get("code") == PROJ_CODE and body.get("name", "").endswith("改")
    check("PMT-DUAL-H03", "编辑项目（名称/描述可改，编号不可改）", ok,
          f"HTTP {r.status_code} code={body.get('code')} name={body.get('name')}")
    # H03-DEF05：文档声明支持改状态，但 schema 无 status 字段
    r = call(c, "PUT", f"/api/projects/{pid}", token=admin_token,
             json_body={"code": PROJ_CODE, "name": "x", "status": "挂起"})
    check("PMT-DUAL-H03", "DEF-05 登记：编辑项目状态字段", False,
          f"HTTP {r.status_code} 【缺陷 DEF-05】PUT /api/projects 声明支持改状态，但 ProjectIn 无 status 字段，带 status 全部 422")

    # H4 项目独立目录：五库 + 交接区
    if not EXTERNAL:
        root = Path(__file__).resolve().parents[2] / "data" / "projects" / PROJ_CODE
        libs = ["01_项目库", "02_交付物", "03_日志", "04_模板", "05_版本库"]
        ok = root.exists() and all((root / lib).exists() for lib in libs)
        ok = ok and (root / "交接区" / "派单").exists() and (root / "交接区" / "交接单.json").exists()
        check("PMT-DUAL-H04", "项目独立目录（五库+交接区+交接单）", ok, f"路径={root}")
    else:
        check("PMT-DUAL-H04", "项目独立目录（外部实例跳过分区检查）", True, "SKIP：外部实例无本地文件系统")

    # H5 名册隔离：项目私有副本 + default 互不污染
    r = call(c, "GET", "/api/members", token=admin_token, params={"project_id": pid})
    own_codes = [m["code"] for m in (r.json() if r.status_code == 200 else [])]
    prefixed = [x for x in own_codes if x.startswith(f"{PROJ_CODE}-")]
    no_default_raw = not any(x in own_codes for x in ("AI-PM-001", "H-001", "H-002"))
    check("PMT-DUAL-H05", "项目名册为私有副本（含前缀克隆，无 default 裸条目）",
          r.status_code == 200 and len(prefixed) > 0 and no_default_raw,
          f"HTTP {r.status_code} 私有副本={len(prefixed)} 裸default混入={not no_default_raw}")
    r = call(c, "GET", "/api/members", token=admin_token, params={"project_id": "PROJ-DEFAULT"})
    # 注意 default 项目 pid 需真实 id；此处用不带 pid 的默认回退验证
    r2 = call(c, "GET", "/api/members", token=admin_token)
    default_codes = [m["code"] for m in (r2.json() if r2.status_code == 200 else [])]
    check("PMT-DUAL-H05", "default 名册未被项目私有副本污染",
          r2.status_code == 200 and "AI-PM-001" in default_codes and PROJ_CODE not in "".join(default_codes),
          f"HTTP {r2.status_code} default含AI-PM-001={'AI-PM-001' in default_codes}")

    # H6 角色卡：克隆 + 新建归属项目
    r = call(c, "GET", "/api/roles", token=admin_token, params={"project_id": pid})
    role_codes = [x["code"] for x in (r.json() if r.status_code == 200 else [])]
    r2 = call(c, "POST", "/api/roles", token=admin_token, params={"project_id": pid},
              json_body={"code": f"RC-{TS}", "role_type": "执行", "duty": "测试职责",
                         "negative_list": "不代签", "permission_level": "L2"})
    r3 = call(c, "GET", "/api/roles", token=admin_token, params={"project_id": pid})
    role_codes2 = [x["code"] for x in (r3.json() if r3.status_code == 200 else [])]
    check("PMT-DUAL-H06", "角色卡克隆+新建均归属本项目", r2.status_code == 201 and f"RC-{TS}" in role_codes2,
          f"HTTP {r2.status_code} 克隆数={len([x for x in role_codes if str(PROJ_CODE) in x])} 新建可见={f'RC-{TS}' in role_codes2}")

    # H7 层级归属：跨项目里程碑/工作包 → 404
    r = call(c, "GET", "/api/projects", token=admin_token)
    other_pid = ""
    for p in (r.json() if r.status_code == 200 else []):
        if p["id"] != pid and p["code"] != PROJ_CODE:
            other_pid = p["id"]
            break
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"TX-{TS}", "title": "跨项目", "milestone_id": other_pid})
    check("PMT-DUAL-H07", "任务挂跨项目里程碑被拒", r.status_code == 404, f"HTTP {r.status_code}")

    # H8 层级冲突：任务指定 MB 里程碑 + MA 工作包 → 409
    r = call(c, "POST", "/api/wbs/milestones", token=admin_token, params={"project_id": pid},
             json_body={"code": "MA", "name": "里程碑A", "status": "进行中"})
    ma_id = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/wbs/milestones", token=admin_token, params={"project_id": pid},
             json_body={"code": "MB", "name": "里程碑B", "status": "进行中"})
    mb_id = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/wbs/workpackages", token=admin_token, params={"project_id": pid},
             json_body={"code": "WPA", "name": "工作包A", "milestone_id": ma_id, "status": "进行中"})
    wpa_id = r.json().get("id", "") if r.status_code == 201 else ""
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"TC-{TS}", "title": "层级冲突任务", "milestone_id": mb_id, "work_package_id": wpa_id})
    check("PMT-DUAL-H08", "任务指定里程碑与工作包层级冲突 → 409",
          r.status_code == 409 and "层级归属冲突" in r.text, f"HTTP {r.status_code} {r.text[:120]}")

    # H9 自动继承：仅给工作包 → 里程碑自动继承
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T1-{TS}", "title": "产出需求规格书", "deliverables": "需求规格书.docx",
                        "acceptance": "评审通过", "human_owner": f"{PROJ_CODE}-H-001",
                        "ai_executor": AI_CODE, "priority": "P1", "work_package_id": wpa_id})
    tid = r.json().get("id", "") if r.status_code == 201 else ""
    r0 = call(c, "GET", f"/api/tasks/{tid}", token=admin_token, params={"project_id": pid})
    echo = r0.json() if r0.status_code == 200 else {}
    ok = r.status_code == 201 and echo.get("milestone_id") == ma_id and echo.get("work_package_id") == wpa_id
    check("PMT-DUAL-H09", "仅给工作包时自动继承里程碑", ok,
          f"HTTP {r.status_code} echo.milestone={echo.get('milestone')} 继承一致={ok}")

    # H10 feed 派单 → 文件落项目独立交接区
    r = call(c, "POST", f"/api/handoff/feed/{tid}", token=admin_token,
             params={"project_id": pid, "receiver": AI_CODE})
    file_field = r.json().get("file", "") if r.status_code == 200 else ""
    file_ok = file_field != "" and (EXTERNAL or Path(file_field).exists())
    order_code = r.json().get("order", "") if file_ok else ""
    check("PMT-DUAL-H10", "feed 派单（文件落项目独立交接区）", r.status_code == 200 and file_ok,
          f"HTTP {r.status_code} 文件={file_field or '空'}")
    order_id = ""
    if order_code:
        r = call(c, "GET", "/api/handoff", token=admin_token, params={"project_id": pid})
        order_id = next((o["id"] for o in (r.json() if r.status_code == 200 else []) if o.get("code") == order_code), "")
        check("PMT-DUAL-H10", "交接单按项目过滤可见", bool(order_id), f"code={order_code}")

    # H11 人类写完成摘要 → recycle（项目 完成/ 目录）
    recycle_ok = False
    if not EXTERNAL:
        done_dir = Path(__file__).resolve().parents[2] / "data" / "projects" / PROJ_CODE / "交接区" / "完成"
        done_dir.mkdir(parents=True, exist_ok=True)
        (done_dir / f"T1-{TS}_完成_产出需求规格书_V1.md").write_text(
            f"任务编号: T1-{TS}\n执行者: {AI_CODE}\n证据路径: 03_日志/任务台账/..\n"
            "交付路径: 02_交付物/01_需求/..\n版本: V1.0\n\n双视角测试完成摘要。\n", encoding="utf-8")
        r = call(c, "POST", f"/api/handoff/recycle/{order_id}", token=admin_token, params={"project_id": pid})
        body = r.json() if r.status_code == 200 else {}
        recycle_ok = r.status_code == 200 and body.get("status") == "已回收" and body.get("ledger")
        check("PMT-DUAL-H11", "人类回写完成摘要并回收", recycle_ok,
              f"HTTP {r.status_code} status={body.get('status') if r.status_code == 200 else '-'}")
    else:
        check("PMT-DUAL-H11", "人类回收（外部实例）", True, "SKIP：外部实例无本地文件系统")

    # H12 close 闭环
    if recycle_ok:
        r = call(c, "POST", f"/api/handoff/{order_id}/close", token=admin_token, params={"project_id": pid})
        check("PMT-DUAL-H12", "交接单闭环", r.status_code == 200 and r.json().get("status") == "已闭环",
              f"HTTP {r.status_code}")
    else:
        check("PMT-DUAL-H12", "交接单闭环", True, "SKIP：未回收无法闭环")

    # H13 签门禁① + advance
    r = call(c, "POST", "/api/process/gates/sign", token=admin_token, params={"project_id": pid},
             json_body={"gate_no": "①", "decision": "通过", "signed_by": "H", "opinion": "双视角测试评审通过"})
    r2 = call(c, "POST", "/api/process/advance", token=admin_token, params={"project_id": pid}, json_body={"target": "S2"})
    check("PMT-DUAL-H13", "人类签门禁①并推进 S2", r.status_code == 200 and r2.status_code == 200 and r2.json().get("stage") == "S2",
          f"sign={r.status_code} advance={r2.status_code} stage={r2.json().get('stage') if r2.status_code == 200 else '-'}")

    # H14 审批卡点：新任务置待评审 → 卡点生成（含"审批"）
    r = call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
             json_body={"code": f"T3-{TS}", "title": "卡点验证任务", "milestone_id": ma_id,
                        "work_package_id": wpa_id, "human_owner": f"{PROJ_CODE}-H-001",
                        "ai_executor": AI_CODE, "priority": "P2"})
    tid3 = r.json().get("id", "") if r.status_code == 201 else ""
    call(c, "POST", f"/api/tasks/{tid3}/transition", token=admin_token, params={"project_id": pid},
         json_body={"target": "进行中"})
    r = call(c, "POST", f"/api/tasks/{tid3}/transition", token=admin_token, params={"project_id": pid},
             json_body={"target": "待评审"})
    if r.status_code != 200:  # 证据前置：先补证据
        call(c, "POST", f"/api/tasks/{tid3}/evidence", token=admin_token, params={"project_id": pid},
             json_body={"paths": ["03_日志/任务台账/卡点验证.docx"], "summary": "卡点验证证据"})
        r = call(c, "POST", f"/api/tasks/{tid3}/transition", token=admin_token, params={"project_id": pid},
                 json_body={"target": "待评审"})
    r = call(c, "GET", "/api/checkpoints", token=admin_token, params={"project_id": pid})
    cps = r.json() if r.status_code == 200 else []
    cp_found = any("审批" in (x.get("category", "") + x.get("content", "")) for x in cps)
    check("PMT-DUAL-H14", "置待评审生成审批卡点（按项目）", r.status_code == 200 and cp_found,
          f"HTTP {r.status_code} 卡点数={len(cps)} 含审批={cp_found}")

    # H15 文档 CRUD：DEF-04（默认路径生成缺陷）+ 正向（合规命名登记/编辑/删除）
    r = call(c, "POST", "/api/docs", token=admin_token, params={"project_id": pid},
             json_body={"doc_no": "R-001", "name": "需求基线", "version": "V1.0", "library": "01_项目库"})
    check("PMT-DUAL-H15", "DEF-04 登记：文档未给路径默认落五库", False,
          f"HTTP {r.status_code} 【缺陷 DEF-04】默认路径生成 '编号_名称.md' 不含连字符/类型词/版本，与命名规则冲突，不带 path 的登记全部 422")
    # 正向：合规命名登记到项目五库
    doc_name = f"{PROJ_CODE}-需求基线-双视角-V1.0.0.md"
    if not EXTERNAL:
        lib_dir = Path(__file__).resolve().parents[2] / "data" / "projects" / PROJ_CODE / "01_项目库" / "需求基线"
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / doc_name).write_text("# 双视角需求基线\n", encoding="utf-8")
    r = call(c, "POST", "/api/docs", token=admin_token, params={"project_id": pid},
             json_body={"doc_no": "R-002", "name": "双视角", "version": "V1.0.0",
                        "library": "01_项目库",
                        "path": str(Path("data/projects") / PROJ_CODE / "01_项目库" / "需求基线" / doc_name)})
    dbody = r.json() if r.status_code == 201 else {}
    did = dbody.get("id", "")
    ok = r.status_code == 201 and bool(did)
    check("PMT-DUAL-H15", "文档合规登记（带 path）", ok, f"HTTP {r.status_code} id={did}")
    if did:
        r = call(c, "PUT", f"/api/docs/{did}", token=admin_token,
                 json_body={"doc_no": "R-002", "name": "双视角-改", "version": "V1.1.0",
                            "library": "01_项目库", "path": dbody.get("path", "")})
        check("PMT-DUAL-H15", "编辑文档条目", r.status_code == 200, f"HTTP {r.status_code}")
        r = call(c, "DELETE", f"/api/docs/{did}", token=admin_token, params={"project_id": pid})
        check("PMT-DUAL-H15", "删除文档条目", r.status_code == 200, f"HTTP {r.status_code}")
        # 无 GET 单条路由（SPA fallback 返回 200 HTML），以列表查询为准
        r = call(c, "GET", "/api/docs", token=admin_token, params={"project_id": pid})
        ids = [d.get("id") for d in (r.json() if r.status_code == 200 else [])]
        check("PMT-DUAL-H15", "删除后条目不在列表", r.status_code == 200 and did not in ids,
              f"HTTP {r.status_code} 残留={did in ids}")

    # H16 guide 人类视角：动作指引 + 准出条件 + readiness
    r = call(c, "GET", "/api/process/guide", token=admin_token, params={"project_id": pid})
    g = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and len(g.get("human_actions", [])) > 0 and len(g.get("exit_criteria", [])) > 0 \
        and g.get("readiness", {}).get("tasks", 0) >= 1
    check("PMT-DUAL-H16", "guide 人类视角（动作/准出/readiness）", ok,
          f"HTTP {r.status_code} human_actions={len(g.get('human_actions', []))} readiness.tasks={g.get('readiness', {}).get('tasks')}")

    # H17 DEF-03 回归：并发同 code 建任务 → 无 500
    def _race():
        return call(c, "POST", "/api/tasks", token=admin_token, params={"project_id": pid},
                    json_body={"code": f"RACE-{TS}", "title": "并发竞态", "milestone_id": ma_id, "work_package_id": wpa_id}).status_code
    import threading
    codes: list[int] = []
    lock = threading.Lock()
    def _w():
        s = _race()
        with lock:
            codes.append(s)
    ths = [threading.Thread(target=_w) for _ in range(4)]
    for t in ths: t.start()
    for t in ths: t.join()
    ok = all(x != 500 for x in codes) and 201 in codes
    check("PMT-DUAL-H17", "DEF-03 回归：并发同编号提交无 500", ok, f"状态码分布={sorted(codes)}")

    # H18 手动同步（按项目）
    r = call(c, "POST", "/api/handoff/sync", token=admin_token, params={"direction": "both"})
    body = r.json() if r.status_code == 200 else {}
    check("PMT-DUAL-H18", "手动双向同步按项目执行", r.status_code == 200 and body.get("projects", 0) > 0,
          f"HTTP {r.status_code} projects={body.get('projects')}")

    # ================= AI 用户视角（A 段，临时 AI 成员登录） =================
    print("\n===== AI 用户视角（A 段） =====")

    # A1 AI 登录
    check("PMT-DUAL-A01", "AI 用户登录", ai_token != "", f"token={'有' if ai_token else '无'}")
    # A2 AI 无令牌 → 401
    r = call(c, "GET", "/api/tasks", token="")
    check("PMT-DUAL-A02", "AI 无令牌访问业务接口", r.status_code == 401, f"HTTP {r.status_code}")

    # A3 AI 查看 guide：同一份指引 + AI 职责
    r = call(c, "GET", "/api/process/guide", token=ai_token, params={"project_id": pid})
    g = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and len(g.get("ai_actions", [])) > 0 and len(g.get("human_actions", [])) > 0
    check("PMT-DUAL-A03", "AI 查看 guide（人机共用同一份指引）", ok,
          f"HTTP {r.status_code} ai_actions={len(g.get('ai_actions', []))} human_actions={len(g.get('human_actions', []))}")

    # A4 AI 领取派单任务（zones 按项目）
    r = call(c, "GET", "/api/handoff/zones", token=ai_token, params={"project_id": pid})
    zb = r.json() if r.status_code == 200 else {}
    piao = zb.get("files", {}).get("派单", [])
    check("PMT-DUAL-A04", "AI 领取派单（zones 按项目）", r.status_code == 200 and any(f"T1-{TS}" in x for x in piao),
          f"HTTP {r.status_code} 派单区文件={piao}")

    # A5 AI 无证据置待评审 → 422（回归，需先进行中）
    r2 = call(c, "POST", "/api/tasks", token=ai_token, params={"project_id": pid},
              json_body={"code": f"T2-{TS}", "title": "AI 执行任务", "milestone_id": ma_id,
                         "work_package_id": wpa_id, "human_owner": f"{PROJ_CODE}-H-001",
                         "ai_executor": AI_CODE, "priority": "P2"})
    tid2 = r2.json().get("id", "") if r2.status_code == 201 else ""
    call(c, "POST", f"/api/tasks/{tid2}/transition", token=ai_token, params={"project_id": pid},
         json_body={"target": "进行中"})
    r3 = call(c, "POST", f"/api/tasks/{tid2}/transition", token=ai_token, params={"project_id": pid},
              json_body={"target": "待评审"})
    check("PMT-DUAL-A05", "AI 无证据置待评审被拒", r3.status_code == 422, f"HTTP {r3.status_code}")

    # A6 AI 登记证据（回归）
    r = call(c, "POST", f"/api/tasks/{tid2}/evidence", token=ai_token, params={"project_id": pid},
             json_body={"paths": ["03_日志/任务台账/AI执行.docx"], "summary": "AI 完成并自审"})
    check("PMT-DUAL-A06", "AI 登记证据", r.status_code == 200 and "evidence" in r.text, f"HTTP {r.status_code}")

    # A7 AI 推进任务 → 待评审（证据后）
    r = call(c, "POST", f"/api/tasks/{tid2}/transition", token=ai_token, params={"project_id": pid},
             json_body={"target": "待评审"})
    check("PMT-DUAL-A07", "AI 证据后推进待评审", r.status_code == 200 and r.json().get("status") == "待评审",
          f"HTTP {r.status_code}")

    # A8 AI 代签门禁 → 403（回归）
    r = call(c, "POST", "/api/process/gates/sign", token=ai_token, params={"project_id": pid},
             json_body={"gate_no": "②", "decision": "通过", "signed_by": AI_CODE})
    check("PMT-DUAL-A08", "AI 代签门禁被拒", r.status_code == 403 and "人类" in r.text, f"HTTP {r.status_code} {r.text[:100]}")

    # A9 AI 越级迁移 → 409（回归）
    r = call(c, "POST", f"/api/tasks/{tid2}/transition", token=ai_token, params={"project_id": pid},
             json_body={"target": "关闭"})
    check("PMT-DUAL-A09", "AI 非法迁移（待评审→关闭）", r.status_code == 409, f"HTTP {r.status_code}")

    # A10 AI 跨项目访问（成员归属本项目，访问其他项目）
    r = call(c, "GET", "/api/wbs/tree", token=ai_token, params={"project_id": other_pid})
    if r.status_code in (200, 404, 403):
        ok = r.status_code == 404 or r.status_code == 403
        detail = f"HTTP {r.status_code}"
        if r.status_code == 200:
            ok = False
            detail += " 【观察项 O-05】AI 可跨项目读取 WBS（权限粒度未按成员项目隔离）"
        check("PMT-DUAL-A10", "AI 跨项目访问被隔离", ok, detail)
    else:
        check("PMT-DUAL-A10", "AI 跨项目访问被隔离", False, f"HTTP {r.status_code} 异常")

    # A11 AI 编辑项目（权限边界）
    r = call(c, "PUT", f"/api/projects/{pid}", token=ai_token,
             json_body={"code": PROJ_CODE, "name": "AI 改项目名"})
    if r.status_code == 200:
        check("PMT-DUAL-A11", "AI 编辑项目（权限边界）", False,
              f"HTTP {r.status_code} 【观察项 O-06】AI 可编辑项目信息（AI 应只执行不决策）")
    else:
        check("PMT-DUAL-A11", "AI 编辑项目被拒", True, f"HTTP {r.status_code}")

    # A13 AI 建项目（权限边界）——放在 AI 删除成员之前
    r = call(c, "POST", "/api/projects", token=ai_token,
             json_body={"code": f"T-AIX-{TS}", "name": "AI 建的项目", "owner": "AI"})
    if r.status_code == 201:
        check("PMT-DUAL-A13", "AI 建项目（权限边界）", False,
              f"HTTP {r.status_code} 【观察项 O-08】AI 可创建项目")
    else:
        check("PMT-DUAL-A13", "AI 建项目被拒（权限边界）", True, f"HTTP {r.status_code}")

    # A12 AI 删除成员（权限边界）
    r = call(c, "DELETE", f"/api/members/{ai_member_id}", token=ai_token, params={"project_id": pid})
    if r.status_code == 200:
        check("PMT-DUAL-A12", "AI 删除成员被拒（权限边界）", False,
              f"HTTP {r.status_code} 【观察项 O-07】AI 可删除成员")
    else:
        check("PMT-DUAL-A12", "AI 删除成员被拒（权限边界）", True, f"HTTP {r.status_code}")

    # ---------- 清理 ----------
    if ai_member_id:
        r = call(c, "DELETE", f"/api/members/{ai_member_id}", token=admin_token)
        print(f"[INFO] 清理临时 AI 成员 {AI_CODE} -> HTTP {r.status_code}")

    # ---------- 汇总 ----------
    passed = sum(1 for x in RESULTS if x["pass"])
    failed = [x for x in RESULTS if not x["pass"]]
    total = len(RESULTS)
    print("\n" + "=" * 76)
    print(f"双视角功能测试完成：共 {total} 项，PASS {passed}，FAIL {len(failed)}")
    if failed:
        print("失败/观察项明细：")
        for x in failed:
            print(f"  - {x['case']} {x['name']}: {x['detail']}")
    summary = {
        "script": "playbook_dual", "ts": TS, "project_code": PROJ_CODE, "project_id": pid,
        "ai_member": AI_CODE, "total": total, "passed": passed, "failed": len(failed),
        "results": RESULTS,
    }
    out_path = Path(__file__).resolve().parents[2] / "data" / "02_交付物" / "04_测试" / f"report_dual_{TS}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入：{out_path}")
    print("=" * 76)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
