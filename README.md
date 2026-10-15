# PM-Collab · 人机共用项目管理软件（个人版 v0.1.0）

把《项目管理 AI（PM-AI）需求规格书》体系落地为可运行软件：人类与 AI 使用同一份数据、同一套流程、同一套留痕。
**单机 SQLite 个人版首发**——开箱即用，无需 PostgreSQL，无需 Node（前端已构建在 `pm-collab/web/dist`）。

技术栈：FastAPI（Python 3.11+）/ SQLAlchemy 2.0 / Vue 3 + Element Plus + ECharts / watchdog / APScheduler。
切换 `PM_DATABASE_URL` 可启用 PostgreSQL 16（同一套 ORM/迁移代码）。

## 特性一览
- 五库文件托管（项目库 / 交付物 / 日志 / 模板 / 版本库）+ 交接总线
- 任务卡状态机、四道流程门禁（**人类签字不可代签**）
- 文档条目登记 + 版本台账（哈希防篡改、只增不改、可基线化）
- 每日摘要、看板 / 时间线 / 泳道三视图、度量与审计日志
- 人类与 AI 成员统一建档、统一编号

## 快速上手（5 分钟）
前置：Python 3.11+。无需 Node。

```bash
git clone https://github.com/<org>/pm-collab.git
cd pm-collab
pip install -r requirements.txt
uvicorn server.app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 http://127.0.0.1:8000 ，**首次启动控制台会打印一次性密码（账号 `admin`）**，复制到登录页即可；登录后请立即通过右上角「修改密码」更换。

> 默认监听 `127.0.0.1`（本机），不暴露公网。JWT 密钥首次启动随机生成并写入 `pm-collab/.env`（已被 `.gitignore` 排除，请勿提交）。

前端开发模式（可选）：

```bash
cd web
npm install
npm run dev     # http://localhost:5173（已配置 /api 代理）
npm run build   # 产物输出到 web/dist，由后端一并托管
```

## 目录结构
```
仓库根/
├── LICENSE            MIT 许可证
├── README.md          本文件
├── CHANGELOG.md       版本记录
├── .gitignore
├── docs/              design / user-guide / testing / third-party-licenses.md
└── pm-collab/         产品代码
    ├── server/        FastAPI 服务层（API · 流程引擎 · 交接总线 · 调度 · 监听）
    ├── web/           Vue 3 前端（src 源码 + dist 构建产物）
    ├── alembic/       数据库迁移
    ├── tests/         单测 + 集成测试（覆盖率 ≥ 80% 为开发准出硬门槛）
    ├── scripts/       smoke / seed / 归档导出 等运维脚本
    ├── data/          文件库（运行时生成，已被 .gitignore 排除）
    └── requirements.txt
```

## 关键规则（代码强制）
| 规则 | 落地位置 |
| --- | --- |
| 8 阶段不可跳过、无门禁签字不放行 | `server/app/state_machine.py` + `api/process.py` |
| 任务状态机非法迁移被拒 | `state_machine.TASK_TRANSITIONS` |
| 无证据不得置「通过」、关闭须有完成摘要 | `api/tasks.py` |
| 追加式日志只增不改不可删 | 迁移触发器 + `services/triggers.py` |
| 交接单 4 态、文件↔库双向同步 | `services/handoff_sync.py` + watchdog |
| 文档命名校验、哈希不匹配即告警 | `utils.validate_doc_name` + `api/docs.py` |
| 门禁签字必须人类（AI 不可代签） | `api/process.py::sign_gate` |

## 运行与验证
```bash
cd pm-collab
pytest                                   # 测试（CI 同款）
PM_COLLAB_PASSWORD=<首次启动打印的密码> python scripts/smoke.py   # 端到端冒烟
```

## 环境变量
| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PM_DATABASE_URL` | `sqlite:///data/pm_collab.db` | 切 PG：`postgresql+psycopg://user:pwd@host:5432/pmcollab` |
| `PM_DATA_DIR` | `pm-collab/data` | 五库与交接区根目录 |
| `PM_SECRET_KEY` | 首启随机生成并写入 `.env` | JWT 签名密钥，务必妥善保存 `.env` |
| `PM_BOOTSTRAP_USERNAME` / `PM_BOOTSTRAP_PASSWORD` | `admin` / 首启随机 | 初始管理员；留空则系统生成一次性口令 |
| `PM_DAILY_DIGEST_HOUR` / `MINUTE` | 8 / 30 | 每日摘要定时 |
| `PM_WATCHDOG_ENABLED` / `PM_SCHEDULER_ENABLED` | true | 交接区监听与定时任务开关 |
| `PM_FEISHU_WEBHOOK` | 空 | 可选推送渠道；留空则本地日志留痕 |

## 文档
- 设计：`docs/design/`（设计大纲、WBS 设计、设计开发流程）
- 使用：`docs/user-guide/`（使用手册、外部 AI 接入指导书）
- 测试：`docs/testing/`（验收测试大纲、实现评审记录）
- 许可：`docs/third-party-licenses.md`

> Issue 欢迎，模板 v0.2 补。
