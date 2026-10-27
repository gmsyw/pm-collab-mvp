# PM-Collab WBS 子任务补充设计

版本：V1.0（补充文档） · 编制日期：2026-10-05 · 状态：待评审
编制依据：《项目管理 AI（PM-AI）需求规格书 V1.0》§4.1（分解层级：项目→里程碑→工作包→任务）、
《人机共用项目管理软件-设计大纲 V0.3》、《PM-Collab MVP 任务分解 V1.0》、《文档组织方案 V1.0》

---

## 1. 背景与定位

需求规格书 §4.1 明确的工作分解层级为 **四层 WBS**：

> 项目（Project）→ 里程碑（Milestone）→ 工作包（WorkPackage）→ 任务（TaskCard）

该层级在原始需求与设计中**未定义"任务之下再拆解"的能力**。在真实研发执行中，单张任务卡往往仍偏粗，
需要再向下拆出更细粒度的可执行单元（例如："编写迁移脚本""补充单测""撰写发布说明"），由不同角色/AI 并行或串行完成，
并单独跟踪状态与证据。

本补充文档在**不改动四层 WBS 既有定义**的前提下，于"任务"之下新增**第五层分解——子任务（SubTask）**，
形成完整的执行分解链：

> 项目 → 里程碑 → 工作包 → 任务 → **子任务**

> 说明：四层 WBS 在本系统中已从原先任务卡上的自由文本字段（`milestone`/`work_package`）升级为**独立实体**
> （`milestones` / `work_packages` 表）并通过外键（`task_cards.milestone_id` / `task_cards.work_package_id`）关联，
> 本补充文档在此基础上补齐最末端的子任务层。

---

## 2. 子任务（SubTask）数据模型

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | String(36) PK | 主键（UUID） |
| project_id | String(36) | 所属项目（多项目隔离，沿用 §2 设计原则） |
| task_id | String(36) | **隶属的任务卡**（TaskCard.id），构成"任务→子任务"父子关系 |
| code | String(64) | 子任务编号，如 `ST-001`（项目内唯一） |
| title | String(256) | 子任务标题/目标 |
| description | Text | 说明 |
| status | String(16) | 状态，**复用任务卡状态机**（见 §3） |
| assignee | String(128) | 负责人（人或 AI 实例） |
| priority | String(8) | 优先级 P0/P1/P2 |
| due_date | String(32) | 截止日期 YYYY-MM-DD |
| evidence | JSON | 证据路径列表（复用"无证据不得置为通过"原则） |
| summary | Text | 完成摘要 |
| order_index | Integer | 排序 |
| extra | JSON | 扩展字段 |
| created_at / updated_at | DateTime | 时间戳 |

- 实体表：`sub_tasks`
- 索引：`ix_sub_tasks_project_id`、`ix_sub_tasks_task_id`
- **只向下拆一层**：子任务之下不再允许继续拆子任务（保持层级清晰、可追溯），如需更细拆分应把父任务整体细化。

---

## 3. 状态机

子任务状态机**直接复用任务卡状态机**（来源：需求书 §4.3），不做二次定义，避免语义分裂：

```
待办 → 进行中 → 待评审 → 通过 → 关闭
              ↘ 阻塞 / 取消
待评审 → 返工 → 进行中
```

- 非法迁移在 API 入口即被拒绝（`can_transit_task`）。
- "无证据不得置为通过"原则适用于子任务（`evidence` 字段）。
- 子任务不单独触发流程门禁，但其完成度可汇总计入父任务的进度看板。

---

## 4. 接口（服务层 API 唯一入口）

前缀 `/api/wbs`，全部按 `project_id` 隔离（沿用既有项目上下文 `project_ctx`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/wbs/milestones` | 里程碑列表 |
| POST | `/api/wbs/milestones` | 新建里程碑 |
| PUT | `/api/wbs/milestones/{id}` | 更新里程碑 |
| DELETE | `/api/wbs/milestones/{id}` | 删除里程碑（含工作包时拒绝） |
| GET | `/api/wbs/workpackages?milestone_id=` | 工作包列表 |
| POST | `/api/wbs/workpackages` | 新建工作包（须指定里程碑） |
| PUT | `/api/wbs/workpackages/{id}` | 更新工作包 |
| DELETE | `/api/wbs/workpackages/{id}` | 删除工作包（含任务时拒绝） |
| GET | `/api/wbs/subtasks?task_id=` | 子任务列表（按任务过滤） |
| POST | `/api/wbs/subtasks` | 新建子任务（须指定 task_id） |
| PUT | `/api/wbs/subtasks/{id}` | 更新子任务 |
| POST | `/api/wbs/subtasks/{id}/transition` | 子任务状态迁移（复用任务卡状态机） |
| POST | `/api/wbs/subtasks/{id}/evidence` | 登记子任务证据 |
| DELETE | `/api/wbs/subtasks/{id}` | 删除子任务 |
| GET | `/api/wbs/tree` | **WBS 树**：项目→里程碑→工作包→任务→子任务 一次性组装，供前端树状视图 |

任务卡创建/更新同时接受 `milestone_id`、`work_package_id`，后端反查并填充冗余展示字段，
保证既有"里程碑/工作包"视图（任务卡页、日报）无需改动即可继续工作。

---

## 5. 前端（WBS 分解视图）

- 新增导航项 **「WBS 分解」**（`/wbs`）：以嵌套卡片呈现四层 + 子任务的完整分解结构。
  - 里程碑卡片 → 工作包卡片 → 任务卡片 → 子任务行。
  - 各层均可在界面内**就地创建/编辑/删除**（里程碑、工作包、子任务）。
  - 子任务行支持状态迁移（下拉选择目标态）与删除。
  - 未归类任务单独列出，便于把游离任务归并到工作包。
- 任务卡页（`/tasks`）：创建表单新增"里程碑""工作包"下拉选择，使任务在创建时即落入 WBS；
  操作列新增"拆解子任务"按钮，一键跳转 WBS 视图对当前任务拆子任务。

---

## 6. 迁移与数据

- 数据库迁移 `b2c3d4e5f6a7_wbs_milestone_workpackage_subtask.py`：
  1. 新建 `milestones` / `work_packages` / `sub_tasks` 三表；
  2. 任务卡表新增 `milestone_id` / `work_package_id` 外键列；
  3. **存量回填**：将既有任务卡的 `milestone`/`work_package` 自由文本升级为实体关联，
     使历史 30 张任务卡继续可见、可追溯（默认项目 MVP、WP0–WP7）。
- 种子数据（`seed_all.py`）同步生成默认里程碑 MVP 与 WP0–WP7，并把示例任务关联到对应工作包。

---

## 7. 追溯矩阵（补充）

| 本补充章节 | 对应来源 |
| --- | --- |
| §1 分解层级扩展 | 需求书 §4.1（四层）+ 本补充新增第五层 |
| §2 子任务模型 | 需求书 §4.2 字段精神（复用任务卡字段约定） |
| §3 状态机 | 需求书 §4.3 |
| §4 接口 | 设计大纲 §2 服务层 API 唯一入口原则 |
| §5 前端 | MVP 任务分解 §3 WP4 前端 |
| §6 迁移 | MVP 任务分解 §2 数据模型 / Alembic |

> 结论：原始需求定义了四层 WBS 但未明确"任务之下再拆子任务"。本补充文档补齐该能力，
> 并将四层 WBS 落地为结构化实体，使 PM-Collab 的分解体系完整覆盖
> **项目 → 里程碑 → 工作包 → 任务 → 子任务** 五级，且人、AI 共用同一套数据与流程。
