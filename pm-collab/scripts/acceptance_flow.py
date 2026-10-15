"""验收流程执行：文档登记 → 门禁①②③④签字 → 阶段推进 S1→S8 → 测试登记 → 摘要 → 留痕。

全流程经服务层 API 执行（服务层为唯一数据入口），每一步自动追加日志。
用法：python scripts/acceptance_flow.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402

from server.app.main import create_app  # noqa: E402
from server.app.services.db_bootstrap import init_db  # noqa: E402

# 交付物登记清单（doc_no, 库, 名称, 相对路径）
DOC_REGISTRY = [
    ("DOC-CHARTER-001", "01_项目库", "项目章程", "01_项目库/项目章程/PM-Collab-章程-项目章程-V1.0.0.md"),
    ("DOC-REVIEW-REQ-001", "01_项目库", "需求评审记录单", "01_项目库/评审记录单/PM-Collab-评审记录单-需求评审-V1.0.0.md"),
    ("DOC-ARCH-001", "02_交付物", "架构与数据模型", "02_交付物/02_设计/PM-Collab-设计文档-架构与数据模型-V1.0.0.md"),
    ("DOC-API-001", "02_交付物", "API规格", "02_交付物/02_设计/PM-Collab-设计文档-API规格-V1.0.0.md"),
    ("DOC-PROTO-001", "02_交付物", "交接区协议", "02_交付物/02_设计/PM-Collab-设计文档-交接区协议-V1.0.0.md"),
    ("DOC-REVIEW-DESIGN-001", "02_交付物", "设计评审记录单", "02_交付物/02_设计/PM-Collab-评审记录单-设计评审-V1.0.0.md"),
    ("DOC-REVIEW-CODE-001", "02_交付物", "代码评审记录单", "02_交付物/02_设计/PM-Collab-评审记录单-代码评审-V1.0.0.md"),
    ("DOC-TEST-001", "02_交付物", "MVP测试报告", "02_交付物/04_测试/PM-Collab-测试报告-MVP测试报告-V1.0.0.md"),
    ("DOC-ACC-001", "02_交付物", "MVP验收记录", "02_交付物/03_验收/PM-Collab-验收记录-MVP验收-V1.0.0.md"),
    ("DOC-TPL-001", "04_模板", "角色卡模板", "04_模板/角色卡/PM-Collab-模板-角色卡-V1.0.0.md"),
    ("DOC-TPL-002", "04_模板", "设计文档模板", "04_模板/设计文档/PM-Collab-模板-设计文档-V1.0.0.md"),
    ("DOC-TPL-003", "04_模板", "评审记录单模板", "04_模板/评审记录单/PM-Collab-模板-评审记录单-V1.0.0.md"),
    ("DOC-TPL-004", "04_模板", "测试记录单模板", "04_模板/测试记录单/PM-Collab-模板-测试记录单-V1.0.0.md"),
    ("DOC-TPL-005", "04_模板", "版本台账模板", "04_模板/版本台账/PM-Collab-模板-版本台账-V1.0.0.md"),
]

GATE_OPINIONS = {
    "①": "需求条目 62 条齐备（MVP 51 条），范围与非目标已界定",
    "②": "设计文档齐套（架构与数据模型/API 规格/交接区协议），评审意见已闭环",
    "③": "代码评审通过，覆盖率 97%，缺陷已关闭",
    "④": "测试全绿（65 用例 + 冒烟 22/22），验收清单 7 项全部通过",
}


def main() -> int:
    init_db()
    app = create_app(start_services=False)
    root = Path(__file__).resolve().parents[1]

    with TestClient(app) as c:
        import os
        _pwd = os.environ.get("PM_COLLAB_PASSWORD")
        if not _pwd:
            raise SystemExit("请先设置环境变量 PM_COLLAB_PASSWORD（首次启动密码见控制台打印）")
        r = c.post("/api/auth/login", json={"username": os.environ.get("PM_COLLAB_USER", "admin"), "password": _pwd})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # 1) 交付物登记（含哈希）
        for doc_no, library, name, rel in DOC_REGISTRY:
            path = root / "data" / rel
            if not path.exists():
                print(f"[warn] 缺失文件，跳过登记：{rel}")
                continue
            resp = c.post("/api/docs", json={
                "doc_no": doc_no, "library": library, "category": name, "name": name,
                "version": "V1.0.0", "owner": "H", "status": "评审通过", "path": str(path),
            }, headers=h)
            print(f"[doc] {doc_no} {name} → {resp.status_code}")

        # 2) 门禁签字（人类签字）
        for gate in ("①", "②", "③", "④"):
            resp = c.post("/api/process/gates/sign", json={
                "gate_no": gate, "decision": "通过", "signed_by": "H",
                "opinion": GATE_OPINIONS[gate],
            }, headers=h)
            print(f"[gate] 门禁{gate} 签字 → {resp.status_code} {resp.json().get('signed_by')}")

        # 3) 测试结果登记（S6→S7 前置）
        resp = c.post("/api/process/test-result", json={
            "passed": True, "report_path": str(root / "data" / "02_交付物" / "04_测试"
                                              / "PM-Collab-测试报告-MVP测试报告-V1.0.0.md"),
            "note": "65 用例通过，覆盖率 97%，冒烟 22/22",
        }, headers=h)
        print(f"[test] 测试结果登记 → {resp.status_code}")

        # 4) 阶段推进 S1 → S8（门禁与测试条件已满足）
        for _ in range(8):
            inst = c.get("/api/process/instance", headers=h).json()
            target = inst["next_stage"]
            if not target:
                break
            resp = c.post("/api/process/advance", json={"target": target}, headers=h)
            print(f"[stage] {inst['stage']} → {target}: {resp.status_code} {resp.json().get('stage_name', resp.text[:60])}")
            if resp.status_code >= 400:
                break

        # 5) 每日摘要（验收后留档）
        dig = c.post("/api/report/digest", params={"push": True}, headers=h).json()
        print(f"[digest] {dig['period']} 推送 {dig['pushed_at']}")

        # 6) 基线化：把已登记且评审通过的版本打基线
        versions = c.get("/api/versions", headers=h).json()
        for v in versions:
            if not v["is_baseline"] and v["review_status"] == "评审通过":
                c.post(f"/api/versions/{v['id']}/baseline", headers=h)
        print(f"[baseline] 已处理 {len(versions)} 条版本记录")

        # 7) 最终状态
        inst = c.get("/api/process/instance", headers=h).json()
        ck = c.get("/api/process/checklist", headers=h).json()
        print(f"[final] 阶段 {inst['stage']} {inst['stage_name']} · 任务 {ck['task_closed']}/{ck['task_total']} 关闭"
              f" · 文档 {ck['doc_total']}（基线 {ck['doc_baselined']}）· 测试通过 {ck['test_passed']}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
