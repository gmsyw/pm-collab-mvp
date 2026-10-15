"""V0.4 过程可视化与结构化字段测试（§4/§11）。

覆盖：任务卡 parent_task_id / module_tag；交接单 event_type / round / evidence；
任务详情时间线（含 event_type 推断）；模块泳道聚合；度量新增平均评审轮次。
"""
from __future__ import annotations


def _task(app_client, headers, code, **kw):
    payload = {"code": code, "title": f"任务 {code}", "acceptance": "可运行"}
    payload.update(kw)
    r = app_client.post("/api/tasks", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _handoff(app_client, headers, code, task_code, **kw):
    payload = {"code": code, "task_code": task_code}
    payload.update(kw)
    r = app_client.post("/api/handoff", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_task_accepts_v04_fields(app_client, headers):
    t = _task(app_client, headers, "T-V01", module_tag="S1", parent_task_id=None)
    assert t["module_tag"] == "S1"
    # 回写校验：更新也接受
    r = app_client.put(f"/api/tasks/{t['id']}", json={"code": "T-V01", "title": "x",
                                                     "module_tag": "S2"}, headers=headers)
    assert r.status_code == 200 and r.json()["module_tag"] == "S2"


def test_handoff_accepts_v04_fields(app_client, headers):
    _task(app_client, headers, "T-V02", module_tag="S1")
    o = _handoff(app_client, headers, "HO-V02", "T-V02",
                 event_type="评审意见", round=2, evidence={"cases": 10, "coverage": "92%", "defects": 0})
    assert o["event_type"] == "评审意见"
    assert o["round"] == 2
    assert o["evidence"]["cases"] == 10


def test_timeline_aggregates_and_infers(app_client, headers):
    _task(app_client, headers, "T-V03", module_tag="S2")
    _handoff(app_client, headers, "HO-A", "T-V03", zone="派单", payload_path="派单/T-V03_任务卡.md")
    _handoff(app_client, headers, "HO-B", "T-V03", event_type="签字",
             payload_path="门禁③_T-V03_签字.md")
    res = app_client.get("/api/viz/timeline", params={"task_code": "T-V03"}, headers=headers).json()
    assert res["task"]["code"] == "T-V03"
    types = {n["event_type"] for n in res["nodes"]}
    # HO-A 无 event_type，按 zone=派单 推断为「派单」
    assert "派单" in types
    # HO-B 显式签字 → 金色高亮标记
    sign = [n for n in res["nodes"] if n["event_type"] == "签字"]
    assert sign and sign[0]["human_sign"] is True and sign[0]["color"] == "gold"


def test_swimlane_aggregates_by_module(app_client, headers):
    _task(app_client, headers, "T-V04", module_tag="S1")
    _task(app_client, headers, "T-V05", module_tag="S1")
    _task(app_client, headers, "T-V06", module_tag="S3")
    res = app_client.get("/api/viz/swimlane", headers=headers).json()
    lanes = {l["module_tag"]: l for l in res["lanes"]}
    assert lanes["S1"]["count"] == 2
    assert lanes["S3"]["count"] == 1
    assert "stage" in lanes["S1"]


def test_metrics_avg_review_rounds(app_client, headers, db):
    _task(app_client, headers, "T-V07", module_tag="S1")
    _handoff(app_client, headers, "HO-R1", "T-V07", event_type="评审意见", round=3)
    _handoff(app_client, headers, "HO-R2", "T-V07", event_type="修订返工", round=1)
    m = app_client.get("/api/report/metrics", headers=headers).json()
    assert "avg_review_rounds" in m
    assert m["avg_review_rounds"] == 2.0
    assert m["review_round_distribution"] == {"3": 1, "1": 1}
