# PM-Collab · 人机共用项目管理软件（MVP）

把《项目管理 AI（PM-AI）需求规格书 V1.0》体系落地为可运行软件：人类与 AI 使用同一份数据、同一套流程、同一套留痕。

技术栈（设计大纲 V0.3 §10）：FastAPI 3.11+ / SQLAlchemy 2.0 + Alembic / PostgreSQL 16（默认降级 SQLite 单机）/ Vue 3 + Element Plus + ECharts / watchdog / APScheduler。

---

## 1. 快速开始（Windows 单机）

```powershell
cd pm-collab
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 1) 初始化数据库（建表 + 追加日志触发器）
.\.venv\Scripts\python scripts/seed.py

# 2) 启动服务（自动托管五库与交接区、启动 watchdog 与每日摘要定时任务）
.\.venv\Scripts\python -m uvicorn server.app.main:app --host 127.0.0.1 --port 8000

# 3) 访问
#    Web UI（已构建）：http://127.0.0.1:8000/
#    API 文档：       http://127.0.0.1:8000/docs
# 默认账号：admin（首次启动密码见控制台打印，登录后请立即修改）
```

前端开发模式（可选）：

```powershell
cd web
npm install
npm run dev     # http://localhost:5173，已配置 /api 与 /ws 代理
npm run build   # 产物输出到 web/dist，由 FastAPI 一并托管
```

## 2. 目录结构

```
pm-collab/
├─ server/          FastAPI 服务层（API · 流程引擎 · 交接总线 · 调度 · 监听）
│  ├─ app/          应用：config / db / models / schemas / state_machine / audit
│  │  ├─ api/       认证 · 名册 · 角色卡 · 任务卡 · 流程门禁 · 文档版本 · 交接 · 卡点 · 报表 · WS
│  │  ├─ services/  five_libs / handoff_sync / watchdog / scheduler / digest / triggers
│  │  └─ main.py
│  └─ seed/         需求条目与角色卡种子数据
├─ web/             Vue 3 前端（看板 / 任务卡 / 交接区卡点 / 流程门禁 / 文档版本）
├─ alembic/         数据库迁移（初版含追加日志触发器与 REVOKE）
├─ tests/           单测 + 集成测试（覆盖率 ≥ 80% 为开发准出硬门槛）
├─ scripts/         seed / smoke / 归档导出 等运维脚本
└─ data/            文件库（软件托管）
   ├─ 01_项目库     章程 · 名册与角色卡 · 需求基线 · 计划与里程碑 · 变更单 · 评审记录单
   ├─ 02_交付物     01_需求 / 02_设计 / 03_验收 / 04_测试 / 代码
   ├─ 03_日志       交互日志 · 任务台账 · 问题与风险台账 · 日报周报
   ├─ 04_模板       角色卡 · 设计文档 · 评审记录单 · 测试记录单 · 版本台账
   ├─ 05_版本库     版本台账 · 发布日志 · archive
   └─ 交接区        派单 / 回执 / 完成 / 评审输入 / 评审输出 / 卡点 + 交接单.json
```

## 3. 关键规则（代码强制）

| 规则 | 落地位置 |
| --- | --- |
| 8 阶段不可跳过、无门禁签字不放行 | `server/app/state_machine.py` + `api/process.py` |
| 任务状态机非法迁移被拒（关闭→待办 等） | `state_machine.TASK_TRANSITIONS` |
| 无证据不得置为「通过」、关闭须有完成摘要 | `api/tasks.py` 迁移校验 |
| 追加式日志只增不改不可删 | 迁移触发器 + `services/triggers.py`（PG 另加 REVOKE） |
| 交接单 4 态、文件↔库双向同步（冲突不计） | `services/handoff_sync.py` + watchdog |
| 文档命名校验、哈希不匹配即告警 | `utils.validate_doc_name` + `api/docs.py` |
| 门禁签字必须人类（AI 不可代签） | `api/process.py::sign_gate` |
| 测试不通过不得进入验收 | `state_machine.TEST_EVIDENCE_ON_ADVANCE` |

## 4. 运行与验证命令

```powershell
.\.venv\Scripts\python -m pytest tests -q --cov=server --cov-report=term-missing  # 测试 + 覆盖率
.\.venv\Scripts\python scripts/smoke.py        # 端到端冒烟（派单→回执→完成→回收→台账）
.\.venv\Scripts\python scripts/seed.py         # 需求条目/角色卡/任务卡种子导入
.\.venv\Scripts\python scripts/export_registers.py  # 名册/需求基线/任务台账/版本台账 导出入五库
.\.venv\Scripts\python -m alembic upgrade head # 数据库迁移（默认连接由 PM_DATABASE_URL 指定）
```

## 5. 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PM_DATABASE_URL` | `sqlite:///data/pm_collab.db` | 切 PG：`postgresql+psycopg://user:pwd@host:5432/pmcollab` |
| `PM_DATA_DIR` | `pm-collab/data` | 五库与交接区根目录 |
| `PM_SECRET_KEY` | 开发用默认值 | JWT 签名密钥，部署必须修改 |
| `PM_DAILY_DIGEST_HOUR/MINUTE` | 8 / 30 | 每日摘要定时 |
| `PM_WATCHDOG_ENABLED` / `PM_SCHEDULER_ENABLED` | true | 交接区监听与定时任务开关 |
| `PM_FEISHU_WEBHOOK` | 空 | 可选推送渠道；留空则本地日志留痕 |
| `PM_BOOTSTRAP_USERNAME/PASSWORD` | admin / （首启随机生成） | 初始人类成员；留空则系统生成一次性口令 |

> 说明：本机未安装 PostgreSQL 16，MVP 默认以 SQLite 单机形态运行（同一套 ORM/迁移代码，切换 `PM_DATABASE_URL` 即启用 PG，触发器与 REVOKE 由 `services/triggers.py` 按方言自动适配）。
