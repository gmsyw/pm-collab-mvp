"""文档条目、版本台账、需求条目与五库托管测试（T12/T07）。"""
from __future__ import annotations

from pathlib import Path


def test_libs_tree_contains_five_libraries(app_client, headers):
    libs = app_client.get("/api/libs/tree", headers=headers).json()["libraries"]
    names = {l["name"] for l in libs}
    assert {"01_项目库", "02_交付物", "03_日志", "04_模板", "05_版本库", "交接区"} <= names


def test_doc_create_naming_validation(app_client, headers, data_dir):
    p = data_dir / "02_交付物" / "02_设计" / "PM-Collab-设计文档-数据模型-V1.0.0.md"
    p.write_text("# 数据模型", encoding="utf-8")
    r = app_client.post("/api/docs", json={"doc_no": "DOC-1", "name": "数据模型",
                                           "path": str(p), "version": "V1.0"}, headers=headers)
    assert r.status_code == 201 and r.json()["file_hash"]

    bad = data_dir / "02_交付物" / "02_设计" / "需求说明最新版.docx"
    bad.write_text("x", encoding="utf-8")
    r = app_client.post("/api/docs", json={"doc_no": "DOC-2", "name": "需求", "path": str(bad)},
                        headers=headers)
    assert r.status_code == 422 and "命名不合规" in r.json()["detail"]


def test_doc_list_filters_and_hash_alert(app_client, headers, data_dir):
    p = data_dir / "02_交付物" / "02_设计" / "PM-Collab-设计文档-API-V1.0.0.md"
    p.write_text("# API 规格", encoding="utf-8")
    created = app_client.post("/api/docs", json={"doc_no": "DOC-3", "name": "API",
                                                 "path": str(p), "library": "02_交付物"},
                              headers=headers).json()
    listed = app_client.get("/api/docs", params={"library": "02_交付物"}, headers=headers).json()
    assert len(listed) == 1
    assert app_client.get("/api/docs", params={"library": "01_项目库"}, headers=headers).json() == []

    ok = app_client.get(f"/api/docs/{created['id']}/verify", headers=headers).json()
    assert ok["alert"] is False and ok["status"] == "哈希一致"

    # 文件被改写 → 告警并生成卡点
    p.write_text("# API 规格（被篡改）", encoding="utf-8")
    bad = app_client.get(f"/api/docs/{created['id']}/verify", headers=headers).json()
    assert bad["alert"] is True and bad["status"] == "哈希不匹配告警"
    ck = app_client.get("/api/checkpoints", headers=headers).json()
    assert any("哈希不匹配" in c["content"] for c in ck)

    assert app_client.get("/api/docs/not-exist/verify", headers=headers).status_code == 404


def test_missing_file_verify_status(app_client, headers):
    created = app_client.post("/api/docs", json={"doc_no": "DOC-4", "name": "幽灵文档",
                                                 "path": "data/not-exists/PM-Collab-测试报告-x-V1.0.0.md"},
                              headers=headers).json()
    res = app_client.get(f"/api/docs/{created['id']}/verify", headers=headers).json()
    assert res["alert"] is True and res["status"] == "文件缺失"


def test_version_ledger_append_only_and_baseline(app_client, headers):
    v1 = app_client.post("/api/versions", json={"version": "V1.0", "item_name": "设计文档",
                                                "review_status": "草稿"}, headers=headers).json()
    v2 = app_client.post("/api/versions", json={"version": "V1.1", "item_name": "设计文档",
                                                "review_status": "评审通过"}, headers=headers).json()
    versions = app_client.get("/api/versions", headers=headers).json()
    assert len(versions) == 2  # 只增不覆盖

    r = app_client.post(f"/api/versions/{v1['id']}/baseline", headers=headers)
    assert r.status_code == 409 and "评审通过" in r.json()["detail"]

    r = app_client.post(f"/api/versions/{v2['id']}/baseline", headers=headers)
    assert r.status_code == 200 and r.json()["is_baseline"] is True
    assert app_client.post("/api/versions/not-exist/baseline", headers=headers).status_code == 404

    filtered = app_client.get("/api/versions", params={"item_name": "设计文档"}, headers=headers).json()
    assert len(filtered) == 2


def test_version_hash_from_file(app_client, headers, data_dir):
    p = data_dir / "05_版本库" / "PM-Collab-版本台账-基线-V1.0.0.md"
    p.write_text("# 台账", encoding="utf-8")
    r = app_client.post("/api/versions", json={"version": "V1.0", "item_name": "台账",
                                               "path": str(p)}, headers=headers)
    assert r.status_code == 201


def test_requirements_seeded(db):
    from server.app.models import RequirementItem
    from server.seed.seed_all import seed_all

    counts = seed_all(db)
    assert counts["requirements"] > 0
    total = db.query(RequirementItem).count()
    assert total == counts["requirements"]
    assert db.query(RequirementItem).filter(RequirementItem.in_mvp.is_(True)).count() > 0
    # 幂等
    assert seed_all(db)["requirements"] == 0


def test_requirements_api(app_client, headers, db):
    from server.seed.seed_all import seed_all

    seed_all(db)
    all_items = app_client.get("/api/requirements", headers=headers).json()
    assert len(all_items) > 50
    mvp = app_client.get("/api/requirements", params={"in_mvp": True}, headers=headers).json()
    assert len(mvp) < len(all_items)
    assert mvp[0]["source_doc"] == "需求规格书 V1.0"


def test_tasks_seed_imports_t01_t25(db):
    from server.app.models import TaskCard
    from server.seed.seed_all import seed_all

    seed_all(db)
    codes = {t.code for t in db.query(TaskCard).all()}
    assert {"T01", "T13", "T25"} <= codes and len(codes) == 25
