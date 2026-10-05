"""L1 对抗与边界用例（N 系列补充 + S3-03 等方案遗留项）。

覆盖点（测试方案 §4.2 / §5.2 中既有 9 个模块未覆盖部分）：
- N-05 / S3-03  不带 project_id 回退默认项目（可检测、可纠正）
- N-06          删除保护：有子项拒绝删除（里程碑/工作包），叶子可删
- N-11          并发重复提交：恰好一个 201、其余 409（幂等/竞态）
- B-03          跨项目引用里程碑 → 404
- C-02（API 面） 子任务状态迁移矩阵 + O-01 观察确认（无证据可直通）
- G（API 面）    版本台账只增不改：无 PUT/DELETE 路由（405）
运行：.venv\\Scripts\\python -m pytest tests/test_l1_adversarial.py -v
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from server.app.models import DEFAULT_PROJECT_ID, Milestone, SubTask, TaskCard, WorkPackage


def _project(app_client, headers, code: str) -> str:
    r = app_client.post("/api/projects", headers=headers, json={"code": code, "name": f"L1-{code}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _milestone(app_client, headers, pid: str, code: str = "M1") -> str:
    r = app_client.post("/api/wbs/milestones", headers=headers, params={"project_id": pid},
                        json={"code": code, "name": "里程碑", "status": "进行中", "owner": "H"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _workpackage(app_client, headers, pid: str, mid: str, code: str = "WP1") -> str:
    r = app_client.post("/api/wbs/workpackages", headers=headers, params={"project_id": pid},
                        json={"milestone_id": mid, "code": code, "name": "工作包"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _task(app_client, headers, pid: str, code: str = "T1", wid: str = "", mid: str = "") -> str:
    body = {"code": code, "title": "L1 任务", "deliverables": "x",
            "acceptance": "y", "human_owner": "H", "ai_executor": "AI-PM-001"}
    if wid:
        body["work_package_id"] = wid
    if mid:
        body["milestone_id"] = mid
    r = app_client.post("/api/tasks", headers=headers, params={"project_id": pid}, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _subtask(app_client, headers, pid: str, tid: str, code: str = "ST1") -> str:
    r = app_client.post("/api/wbs/subtasks", headers=headers, params={"project_id": pid},
                        json={"task_id": tid, "code": code, "title": "子任务"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------- N-05 / S3-03：默认项目回退 ----------------
def test_n05_default_project_fallback(app_client, headers, db):
    """不带 project_id 建里程碑 → 落入默认项目（可检测、可纠正）。"""
    r = app_client.post("/api/wbs/milestones", headers=headers,
                        json={"code": "M-DEF", "name": "回退默认", "status": "进行中", "owner": "H"})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    obj = db.get(Milestone, mid)
    assert obj.project_id == DEFAULT_PROJECT_ID, f"未回退默认项目：{obj.project_id}"
    # 不带 project_id 查询（默认项目视角）可见
    r2 = app_client.get("/api/wbs/milestones", headers=headers)
    assert r2.status_code == 200
    assert any(x["code"] == "M-DEF" for x in r2.json())


# ---------------- N-06：删除保护 ----------------
def test_n06_delete_protected_milestone(app_client, headers):
    """三层删除保护：
    - 里程碑下有工作包 → DELETE 409
    - 工作包下有任务 → DELETE 409
    - 任务无 DELETE 路由（405，只增不改设计：任务只能推进/取消，不可物理删除）
    """
    pid = _project(app_client, headers, "L1-DEL")
    mid = _milestone(app_client, headers, pid)
    wid = _workpackage(app_client, headers, pid, mid)
    _task(app_client, headers, pid, "T1", wid=wid, mid=mid)  # 任务挂到工作包下
    r = app_client.delete(f"/api/wbs/milestones/{mid}", headers=headers, params={"project_id": pid})
    assert r.status_code == 409, r.text
    r = app_client.delete(f"/api/wbs/workpackages/{wid}", headers=headers, params={"project_id": pid})
    assert r.status_code == 409, r.text  # 工作包下有任务 → 409
    tid = _task(app_client, headers, pid, "T-X")
    r = app_client.delete(f"/api/tasks/{tid}", headers=headers, params={"project_id": pid})
    assert r.status_code == 405, f"任务无 DELETE 路由（只增不改设计），实际 {r.status_code}"


def test_n06b_delete_leaf_subtask_ok(app_client, headers, db):
    """叶子子任务可直接删除，删除后树不可见。"""
    pid = _project(app_client, headers, "L1-DEL2")
    mid = _milestone(app_client, headers, pid)
    wid = _workpackage(app_client, headers, pid, mid)
    tid = _task(app_client, headers, pid)
    sid = _subtask(app_client, headers, pid, tid)
    r = app_client.delete(f"/api/wbs/subtasks/{sid}", headers=headers, params={"project_id": pid})
    assert r.status_code == 200, r.text
    assert db.get(SubTask, sid) is None
    tree = app_client.get("/api/wbs/tree", headers=headers, params={"project_id": pid}).json()
    subtask_codes = [s["code"] for m in tree["milestones"] for w in m["work_packages"]
                     for t in w["tasks"] for s in t["sub_tasks"]]
    assert "ST1" not in subtask_codes


# ---------------- N-11：并发重复提交 ----------------
def test_n11_concurrent_duplicate_submit(app_client, headers):
    """并发同 code 建任务：恰好一个 201、其余 409（幂等/竞态无脏数据）。

    当前实现缺陷（DEF-03）：并发下两个请求同时通过查重，flush 时 DB 唯一约束
    IntegrityError 未被捕获 → 其中一个返回 500。修复后此用例应全绿。
    """
    pid = _project(app_client, headers, "L1-CONC")
    body = {"code": "T-CONC", "title": "并发任务", "deliverables": "x", "acceptance": "y",
            "human_owner": "H", "ai_executor": "AI-PM-001", "priority": "P1"}

    def post(_):
        return app_client.post("/api/tasks", headers=headers, params={"project_id": pid}, json=body)

    with ThreadPoolExecutor(max_workers=4) as ex:
        rs = list(ex.map(post, range(4)))
    codes = sorted(r.status_code for r in rs)
    assert codes == [201, 409, 409, 409], f"并发结果异常：{codes} {[r.text[:80] for r in rs]}"
    # 库内恰好一条
    q = app_client.get("/api/tasks", headers=headers, params={"project_id": pid}).json()
    assert len([t for t in q if t["code"] == "T-CONC"]) == 1


# ---------------- B-03：跨项目引用 ----------------
def test_b03_cross_project_reference_rejected(app_client, headers):
    """A 项目的工作包引用 B 项目的里程碑 → 404（跨项目引用拒绝）。"""
    pid_a = _project(app_client, headers, "L1-XA")
    pid_b = _project(app_client, headers, "L1-XB")
    mid_b = _milestone(app_client, headers, pid_b, "M-B")
    r = app_client.post("/api/wbs/workpackages", headers=headers, params={"project_id": pid_a},
                        json={"milestone_id": mid_b, "code": "WP-X", "name": "跨项目"})
    assert r.status_code == 404, r.text


# ---------------- C-02（API 面）：子任务迁移矩阵 + O-01 ----------------
def test_c02_subtask_transition_matrix_via_api(app_client, headers):
    """子任务状态迁移（API 面）：
    - 合法链 待办→进行中→待评审→通过→关闭 全通
    - 无证据/无摘要也可推进（O-01 观察确认：子任务无证据前置检查）
    - 非法迁移 关闭→待办 409；越级 待办→通过 409
    """
    pid = _project(app_client, headers, "L1-ST")
    mid = _milestone(app_client, headers, pid)
    wid = _workpackage(app_client, headers, pid, mid)
    tid = _task(app_client, headers, pid)
    sid = _subtask(app_client, headers, pid, tid)

    def trg(target):
        return app_client.post(f"/api/wbs/subtasks/{sid}/transition", headers=headers,
                               params={"project_id": pid}, json={"target": target})

    # 越级 待办→通过（有状态机拦截）
    assert trg("通过").status_code == 409
    for target in ("进行中", "待评审", "通过", "关闭"):   # O-01：无证据仍全链放行
        r = trg(target)
        assert r.status_code == 200, f"{target} -> {r.status_code} {r.text}"
    assert trg("待办").status_code == 409  # 关闭→待办 非法
    # 非法 target 值
    assert trg("不存在").status_code == 422


# ---------------- G（API 面）：版本台账只增不改 ----------------
def test_g_version_ledger_append_only_api(app_client, headers):
    """版本台账无 PUT/DELETE 路由（只增不改的 API 面，配合 DB 层不可改测试）。"""
    assert app_client.put("/api/versions/whatever", headers=headers, json={}).status_code == 405
    assert app_client.delete("/api/versions/whatever", headers=headers).status_code == 405
    assert app_client.put("/api/versions/whatever/baseline", headers=headers, json={}).status_code == 405
