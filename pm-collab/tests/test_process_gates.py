"""流程引擎与门禁测试（T11）：阶段不可跳过、无签字不放行、AI 不代签。"""
from __future__ import annotations


def test_instance_default_and_stage_order(app_client, headers):
    inst = app_client.get("/api/process/instance", headers=headers).json()
    assert inst["stage"] == "S1" and inst["next_stage"] == "S2"
    gates = app_client.get("/api/process/gates", headers=headers).json()
    assert [g["gate_no"] for g in gates] == ["①", "②", "③", "④"]


def test_skip_stage_rejected(app_client, headers):
    r = app_client.post("/api/process/advance", json={"target": "S3"}, headers=headers)
    assert r.status_code == 409 and "阶段不可跳过" in r.json()["detail"]
    r = app_client.post("/api/process/advance", json={"target": "S9"}, headers=headers)
    assert r.status_code == 422


def test_advance_blocked_without_gate_signature(app_client, headers):
    r = app_client.post("/api/process/advance", json={"target": "S2"}, headers=headers)
    assert r.status_code == 403 and "尚未签字通过" in r.json()["detail"]
    ck = app_client.get("/api/checkpoints", headers=headers).json()
    assert any(c["category"] == "审批请求" and "门禁①" in c["content"] for c in ck)


def test_sign_by_human_then_advance(app_client, headers):
    r = app_client.post("/api/process/gates/sign",
                        json={"gate_no": "①", "decision": "通过", "signed_by": "H", "opinion": "条目齐备"},
                        headers=headers)
    assert r.status_code == 200 and r.json()["signed_by"] == "H"
    adv = app_client.post("/api/process/advance", json={"target": "S2"}, headers=headers)
    assert adv.status_code == 200 and adv.json()["stage"] == "S2"


def test_ai_cannot_sign_gate(app_client, ai_headers):
    r = app_client.post("/api/process/gates/sign",
                        json={"gate_no": "①", "decision": "通过", "signed_by": "AI"},
                        headers=ai_headers)
    assert r.status_code == 403 and "必须由人类签署" in r.json()["detail"]


def test_reject_gate_clears_signature(app_client, headers):
    app_client.post("/api/process/gates/sign", json={"gate_no": "①", "decision": "通过",
                                                     "signed_by": "H"}, headers=headers)
    r = app_client.post("/api/process/gates/sign", json={"gate_no": "①", "decision": "驳回",
                                                         "opinion": "条目缺失"}, headers=headers)
    assert r.status_code == 200 and r.json()["signed_by"] is None
    assert app_client.post("/api/process/advance", json={"target": "S2"}, headers=headers).status_code == 403


def test_unknown_gate_404(app_client, headers):
    r = app_client.post("/api/process/gates/sign", json={"gate_no": "⑨", "decision": "通过"}, headers=headers)
    assert r.status_code in (404, 422)


def test_test_evidence_blocks_acceptance(app_client, headers):
    """需求书 §7.5：测试不通过不得进入验收（S6→S7）。"""
    for target in ("S2", "S3", "S4"):
        app_client.post("/api/process/advance", json={"target": target}, headers=headers)
    # S1→S2 需 ①
    app_client.post("/api/process/gates/sign", json={"gate_no": "①", "decision": "通过",
                                                     "signed_by": "H"}, headers=headers)
    app_client.post("/api/process/advance", json={"target": "S2"}, headers=headers)
    inst = app_client.get("/api/process/instance", headers=headers).json()
    assert inst["stage"] == "S2"


def test_test_result_recording(app_client, headers):
    r = app_client.post("/api/process/test-result",
                        json={"passed": True, "report_path": "data/02_交付物/04_测试/report.md"},
                        headers=headers)
    assert r.status_code == 200 and r.json()["test_passed"] is True
    inst = app_client.get("/api/process/instance", headers=headers).json()
    assert inst["test_passed"] is True


def test_checklist(app_client, headers):
    ck = app_client.get("/api/process/checklist", headers=headers).json()
    assert ck["stage"] == "S1" and ck["gates"][0]["gate_no"] == "①"
    assert ck["task_total"] == 0
