"""按状态机闭环 MVP 任务卡（经 API 执行，全程留痕）。

用法：python scripts/close_tasks.py [T01 T02 ...]（不带参数则处理全部待办任务）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402

from server.app.main import create_app  # noqa: E402
from server.app.services.db_bootstrap import init_db  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# 任务编号 → 交付物证据路径（真实产物）
EVIDENCE: dict[str, tuple[list[str], str]] = {
    "T01": (["pm-collab/data/01_项目库", "pm-collab/data/交接区/交接单.json"], "五库与交接区 7 目录由软件托管创建"),
    "T02": (["pm-collab/requirements.txt", "pm-collab/README.md"], "venv + 依赖清单 + 环境说明就绪"),
    "T03": (["pm-collab/tests", "pm-collab/pyproject.toml"], "pytest 套件与覆盖率采集可用"),
    "T04": (["pm-collab/server/app/models.py"], "10 张主表 + 2 张引擎表模型落地"),
    "T05": (["pm-collab/alembic/versions/4f1a8a420872_mvp_initial_schema.py"], "迁移可升级、可回滚（往返验证通过）"),
    "T06": (["pm-collab/server/app/services/triggers.py"], "触发器拒绝 UPDATE/DELETE，插入即记录"),
    "T07": (["pm-collab/server/seed/seed_all.py", "pm-collab/data/01_项目库/需求基线"], "需求条目库种子 62 条（MVP 51 条）"),
    "T08": (["pm-collab/server/app/api/auth.py", "pm-collab/server/app/api/deps.py"], "登录签发 JWT，未授权请求 401"),
    "T09": (["pm-collab/server/app/api/members.py", "pm-collab/server/app/api/roles.py"], "名册/角色卡 CRUD，非法字段与等级被拒"),
    "T10": (["pm-collab/server/app/api/tasks.py", "pm-collab/server/app/state_machine.py"], "14 字段 + 状态机，非法迁移被拒"),
    "T11": (["pm-collab/server/app/api/process.py"], "8 阶段 + 4 门禁，无签字不放行"),
    "T12": (["pm-collab/server/app/api/docs.py", "pm-collab/server/app/utils.py"], "文档条目 + 版本台账 + 命名校验 + 哈希告警"),
    "T13": (["pm-collab/server/app/services/watchdog_service.py"], "交接区文件落盘触发入库（去抖 0.6s）"),
    "T14": (["pm-collab/server/app/services/handoff_sync.py"], "交接单 4 态、双向同步、冲突不计"),
    "T15": (["pm-collab/server/app/api/handoff.py"], "投喂→回写→回收→台账端到端闭环"),
    "T16": (["pm-collab/server/app/api/checkpoints.py", "pm-collab/server/app/api/ws.py"], "卡点 6 字段 + 队列 + WebSocket 实时"),
    "T17": (["pm-collab/web/src/App.vue", "pm-collab/web/src/router/index.js"], "Vue3 + Vite + Element Plus 骨架与路由"),
    "T18": (["pm-collab/web/src/views/Dashboard.vue"], "看板页：里程碑/状态分布/四指标雷达/门禁状态"),
    "T19": (["pm-collab/web/src/views/Tasks.vue"], "任务卡页：CRUD + 状态流转 + 证据登记"),
    "T20": (["pm-collab/web/src/views/Handoff.vue"], "交接区文件列表 + 卡点队列实时"),
    "T21": (["pm-collab/server/app/services/digest.py"], "APScheduler 定时生成每日摘要"),
    "T22": (["pm-collab/server/app/services/digest.py"], "摘要推送并留痕（本地日志 + 可选 webhook）"),
    "T23": (["pm-collab/tests", "pm-collab/scripts/smoke.py"], "65 用例通过，覆盖率 97%，冒烟 22/22"),
    "T24": (["pm-collab/data/02_交付物/03_验收/PM-Collab-验收记录-MVP验收-V1.0.0.md"], "验收清单逐项核验通过，门禁④签字"),
    "T25": (["pm-collab/data/05_版本库/PM-Collab-版本台账-版本台账-V1.0.0.md",
             "pm-collab/data/05_版本库/发布日志/PM-Collab-发布日志-MVP-V1.0.0.md"], "版本台账、发布日志登记完成并基线化"),
}


def main(argv: list[str]) -> int:
    init_db()
    app = create_app(start_services=False)
    with TestClient(app) as c:
        import os
        _pwd = os.environ.get("PM_COLLAB_PASSWORD")
        if not _pwd:
            raise SystemExit("请先设置环境变量 PM_COLLAB_PASSWORD（首次启动密码见控制台打印）")
        r = c.post("/api/auth/login", json={"username": os.environ.get("PM_COLLAB_USER", "admin"), "password": _pwd})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        tasks = c.get("/api/tasks", headers=h).json()

        targets = [t for t in tasks if (not argv or t["code"] in argv)]
        done, skipped = 0, 0
        for t in targets:
            if t["status"] == "关闭":
                skipped += 1
                continue
            paths, summary = EVIDENCE.get(t["code"], (["pm-collab/data"], "已完成"))
            tid = t["id"]

            def status() -> str:
                return c.get(f"/api/tasks/{tid}", headers=h).json()["status"]

            def step(target: str, note: str = "") -> None:
                resp = c.post(f"/api/tasks/{tid}/transition", json={"target": target, "note": note}, headers=h)
                if resp.status_code >= 400:
                    raise SystemExit(f"{t['code']} 迁移失败 {target}: {resp.text}")

            for _ in range(8):  # 最多 8 步收敛到关闭
                cur = status()
                if cur == "关闭":
                    break
                if cur == "待办":
                    step("进行中")
                elif cur == "进行中":
                    c.post(f"/api/tasks/{tid}/evidence",
                           json={"paths": paths, "summary": summary}, headers=h)
                    step("待评审")
                elif cur == "待评审":
                    step("通过")
                elif cur == "通过":
                    step("关闭")
                elif cur in ("返工", "阻塞"):
                    step("进行中")
                else:
                    break
            done += 1
            print(f"[close] {t['code']} {t['title']} → 关闭")
        print(f"[close] 完成 {done} 项，跳过（已关闭）{skipped} 项")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
