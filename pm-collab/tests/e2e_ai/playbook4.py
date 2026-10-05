"""剧本4 端到端执行脚本：文档版本与基线闭环。

运行：.venv\\Scripts\\python tests\\e2e_ai\\playbook4.py
对应用例：PMT-AI4-*（文档/版本/检查点专项）
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8731"
TS = datetime.datetime.now().strftime("%H%M%S")
PROJ_CODE = f"T-AI4-{TS}"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TEST_DIR = DATA_DIR / "02_交付物" / "04_测试"
RESULTS: list[dict] = []


def check(case_id: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"case": case_id, "name": name, "pass": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {case_id} {name}" + (f" | {detail}" if detail else ""))


def call(client, method, path, token="", params=None, json_body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, f"{BASE}{path}", headers=headers, params=params, json=json_body)


def main() -> int:
    c = httpx.Client(timeout=20)
    r = call(c, "POST", "/api/auth/login", json_body={"username": "admin", "password": "REMOVED-FOR-OPENSOURCE"})
    ok = r.status_code == 200 and "access_token" in r.text
    check("PMT-AI4-S0-01", "登录", ok, f"HTTP {r.status_code}")
    token = r.json()["access_token"] if ok else ""

    r = call(c, "POST", "/api/projects", token=token, json_body={"code": PROJ_CODE, "name": f"剧本4 {TS}"})
    pid = r.json().get("id", "") if r.status_code == 201 else ""
    check("PMT-AI4-S1-01", "建项目", r.status_code == 201, f"HTTP {r.status_code}")

    # ---- 需求条目库（追溯矩阵左端）----
    r = call(c, "GET", "/api/requirements", token=token)
    reqs = r.json() if r.status_code == 200 else []
    check("PMT-AI4-S2-01", "需求条目库非空", r.status_code == 200 and len(reqs) > 0, f"HTTP {r.status_code} 条目数={len(reqs)}")

    # ---- 五库托管 ----
    r = call(c, "GET", "/api/libs/tree", token=token)
    libs = (r.json() or {}).get("libraries", []) if r.status_code == 200 else []
    check("PMT-AI4-S2-02", "五库+交接区托管可见", r.status_code == 200 and len(libs) >= 5, f"HTTP {r.status_code} 目录数={len(libs)}")

    # ---- 登记合规文档（真实文件）----
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    doc_file = TEST_DIR / f"{PROJ_CODE}-测试报告-剧本4-V1.0.0.md"
    doc_file.write_text("# 剧本4 测试文档\n初始内容。\n", encoding="utf-8")
    r = call(c, "POST", "/api/docs", token=token, params={"project_id": pid}, json_body={
        "doc_no": f"TC-{TS}", "library": "04_测试", "category": "测试报告",
        "name": "剧本4测试文档", "version": "V1.0.0", "owner": "QA-AI",
        "status": "评审中", "path": str(doc_file)})
    doc_id = r.json().get("id", "") if r.status_code == 201 else ""
    check("PMT-AI4-S3-01", "登记合规文档", r.status_code == 201 and r.json().get("file_hash"),
          f"HTTP {r.status_code} hash={str(r.json().get('file_hash'))[:12] if r.status_code == 201 else '-'}")

    # ---- 命名不合规 ----
    r = call(c, "POST", "/api/docs", token=token, params={"project_id": pid}, json_body={
        "doc_no": f"BAD-{TS}", "library": "04_测试", "category": "测试报告",
        "name": "非法命名", "version": "V1.0.0", "owner": "QA-AI", "status": "草稿",
        "path": str(TEST_DIR / f"{PROJ_CODE}-随便名称-剧本4-V1.0.0.md")})
    check("PMT-AI4-S3-02", "文档命名不合规被拒", r.status_code == 422, f"HTTP {r.status_code} {r.text[:120]}")

    # ---- 哈希一致 ----
    r = call(c, "GET", f"/api/docs/{doc_id}/verify", token=token)
    body = r.json() if r.status_code == 200 else {}
    check("PMT-AI4-S4-01", "verify 哈希一致", r.status_code == 200 and body.get("status") == "哈希一致" and not body.get("alert"),
          f"HTTP {r.status_code} {body.get('status')}")

    # ---- 篡改后告警 + 卡点 ----
    with doc_file.open("a", encoding="utf-8") as f:
        f.write("\n# 被篡改的内容\n")
    r = call(c, "GET", f"/api/docs/{doc_id}/verify", token=token)
    body = r.json() if r.status_code == 200 else {}
    check("PMT-AI4-S4-02", "篡改后 verify 告警", r.status_code == 200 and body.get("alert") is True,
          f"HTTP {r.status_code} status={body.get('status')}")
    r = call(c, "GET", "/api/checkpoints", token=token, params={"project_id": pid})
    cp_hit = r.status_code == 200 and "哈希" in r.text
    check("PMT-AI4-S4-03", "哈希告警生成卡点", cp_hit, f"HTTP {r.status_code} 含哈希卡点={cp_hit}")

    # ---- 版本台账：不覆盖 ----
    v1 = call(c, "POST", "/api/versions", token=token, params={"project_id": pid}, json_body={
        "version": "V1.0.0", "item_name": "需求基线", "item_type": "文档",
        "executor": "QA-AI", "change_summary": "首版", "review_status": "草稿"})
    v2 = call(c, "POST", "/api/versions", token=token, params={"project_id": pid}, json_body={
        "version": "V1.1.0", "item_name": "需求基线", "item_type": "文档",
        "executor": "QA-AI", "change_summary": "修订", "review_status": "评审通过"})
    v1_id = v1.json().get("id", "") if v1.status_code == 201 else ""
    v2_id = v2.json().get("id", "") if v2.status_code == 201 else ""
    r = call(c, "GET", "/api/versions", token=token, params={"project_id": pid, "item_name": "需求基线"})
    versions = r.json() if r.status_code == 200 else []
    check("PMT-AI4-S5-01", "版本不覆盖（两次登记两条记录）",
          v1.status_code == 201 and v2.status_code == 201 and len(versions) == 2,
          f"V1={v1.status_code} V2={v2.status_code} 记录数={len(versions)}")

    # ---- 基线化限制 ----
    r = call(c, "POST", f"/api/versions/{v1_id}/baseline", token=token)
    check("PMT-AI4-S5-02", "草稿版本基线化被拒", r.status_code == 409, f"HTTP {r.status_code}")
    r = call(c, "POST", f"/api/versions/{v2_id}/baseline", token=token)
    check("PMT-AI4-S5-03", "评审通过版本基线化成功", r.status_code == 200 and r.json().get("is_baseline") is True,
          f"HTTP {r.status_code}")

    # ---- 检查点：6 字段 + 处理 ----
    r = call(c, "POST", "/api/checkpoints", token=token, params={"project_id": pid}, json_body={
        "trigger": "PM-AI", "content": "剧本4 文档基线已建立，请人工复核",
        "human_action": "复核基线版本 V1.1.0", "expect_by": "当日",
        "task_code": "T4-1", "category": "审批请求"})
    cp_id = r.json().get("id", "") if r.status_code == 201 else ""
    check("PMT-AI4-S6-01", "生成检查点（6 字段）", r.status_code == 201 and bool(cp_id), f"HTTP {r.status_code}")
    r = call(c, "GET", "/api/checkpoints", token=token, params={"project_id": pid})
    cps = r.json() if r.status_code == 200 else []
    fields = {"occurred_at", "trigger", "content", "human_action", "expect_by", "task_code", "category"}
    ok = r.status_code == 200 and any(cp.get("id") == cp_id and fields.issubset(cp.keys()) for cp in cps)
    check("PMT-AI4-S6-02", "检查点字段完整可查", ok, f"HTTP {r.status_code} 卡点数={len(cps)}")
    r = call(c, "POST", f"/api/checkpoints/{cp_id}/handle", token=token, json_body={"note": "已复核，确认无误"})
    check("PMT-AI4-S6-03", "处理检查点", r.status_code == 200 and r.json().get("status") == "已处理", f"HTTP {r.status_code}")

    # ---- 汇总 ----
    passed = sum(1 for x in RESULTS if x["pass"])
    failed = [x for x in RESULTS if not x["pass"]]
    print("\n" + "=" * 60)
    print(f"剧本4 完成：共 {len(RESULTS)} 项，PASS {passed}，FAIL {len(failed)}")
    for x in failed:
        print(f"  - {x['case']} {x['name']}: {x['detail']}")
    out = Path(__file__).resolve().parents[2] / "data" / "02_交付物" / "04_测试" / f"report_playbook4_{TS}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"script": "playbook4", "ts": TS, "project_code": PROJ_CODE, "project_id": pid,
                               "doc_file": str(doc_file), "total": len(RESULTS), "passed": passed,
                               "failed": len(failed), "results": RESULTS},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告：{out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
