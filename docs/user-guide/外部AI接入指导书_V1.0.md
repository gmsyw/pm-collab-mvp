# PM-Collab 外部 AI 接入指导书

版本：V1.0 · 编制日期：2026-10-05 · 状态：对外发布
适用对象：具备工具调用（function calling / MCP / 插件）能力的 AI，例如
**豆包（字节）智能体、Claude、GPT、CodeBuddy / 其他本地或云端 Agent**。

---

## 0. 结论：可以让 AI 使用吗？

**可以。** PM-Collab 的设计原则之一是"**服务层 API 唯一入口**"——所有功能（项目、WBS、
任务、门禁、交接、日报、文档）都通过一套标准 REST API 暴露。任何能发起 HTTP 请求的
AI / 智能体都能登录后调用这些接口，完成"新建项目 → 分解 WBS → 派单执行 → 门禁把关 →
交接归档"的全流程管理。

> 前提：AI 必须能**网络可达**该服务（见 §1 的可达性说明，这是唯一硬性约束）。

---

## 1. 可达性（最重要的一步）

PM-Collab 是运行在你机器上的本地服务（FastAPI，默认地址 `http://127.0.0.1:8731`）。

| AI 部署形态 | 能否直接访问 127.0.0.1:8731 | 做法 |
| --- | --- | --- |
| **本机 Agent**（如 CodeBuddy 本机运行、本地 Python 脚本、本地 MCP Server） | ✅ 可以 | 直接用 `http://127.0.0.1:8731` 作为 BASE_URL |
| **云端 AI**（豆包网页/API、Claude API、GPT 等） | ❌ 默认不行 | 需二选一：① 把服务部署到**云端/内网可达地址**（CloudStudio、云服务器、内网穿透），BASE_URL 指向该地址；② 在**本机运行一个 MCP Server** 封装 PM-Collab API，云端 AI 通过 MCP 协议经本机桥接调用（推荐，数据不出本机网络） |

> 换句话说：豆包/Claude 这类云端模型**不是"不能"用，而是需要一个可达的入口**。
> 最简单稳妥的方案是"本机 MCP 桥"——在本机启动一个 MCP Server，把下方接口包成工具，
> 云端 AI 通过 MCP 调用，本机服务无需暴露公网。

---

## 2. 连接与认证

### 2.1 默认账号（MVP 单用户）
- 用户名：`admin`
- 密码：`首次启动随机口令`
- （来自配置 `settings.bootstrap_username/password`，可自行修改）

### 2.2 登录拿令牌
```http
POST {BASE}/api/auth/login
Content-Type: application/json

{ "username": "admin", "password": "首次启动随机口令" }
```
返回：
```json
{ "access_token": "<JWT>", "username": "admin" }
```
- 之后**每个请求**都带请求头：
  ```
  Authorization: Bearer <access_token>
  ```
- 未带令牌或令牌无效 → `401`。

### 2.3 选择"当前项目"
所有业务数据按 `project_id` 隔离。两种做法：
- **推荐**：每个请求追加查询参数 `?project_id=<项目id>`。
- 若省略：服务端自动回退到"第一个项目 / 默认项目（PM-Collab 示范项目）"。

> 新建项目后，务必把返回的新项目 `id` 记下来，后续所有 WBS/任务/门禁请求都带上
> `?project_id=<新项目id>`，否则会写到默认项目里。

---

## 3. AI 管理一个项目的标准流程（含示例）

下面以"新建项目 → 建里程碑 → 建工作包 → 建任务 → 拆子任务 → 推进状态"为主线，
给出可直接套用的请求示例（以 `curl` 演示；AI 工具调用时把对应字段转成 JSON 入参即可）。

约定：`$TOKEN` 为登录拿到的 `access_token`；`$PID` 为目标项目 `id`。

### Step 1 · 登录
```bash
curl -s -X POST {BASE}/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"首次启动随机口令"}'
# => {"access_token":"...","username":"admin"}
```

### Step 2 · 新建项目
```bash
curl -s -X POST {BASE}/api/projects \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"code":"PROJ-AI","name":"AI 试点项目","description":"由 AI 协助管理","owner":"Dr Ming"}'
# => {"id":"<PID>","code":"PROJ-AI","name":"AI 试点项目"}
```
> 新项目会自动初始化"独立流程实例 + 4 个门禁"，无需手动建。

### Step 3 · 在该项目下建里程碑
```bash
curl -s -X POST "{BASE}/api/wbs/milestones?project_id=$PID" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"code":"M1","name":"需求与方案","status":"进行中","owner":"Dr Ming"}'
# => {"id":"<MID>","code":"M1","name":"需求与方案", ...}
```

### Step 4 · 建工作包（必须属于某个里程碑）
```bash
curl -s -X POST "{BASE}/api/wbs/workpackages?project_id=$PID" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"milestone_id":"<MID>","code":"WP1","name":"需求调研","status":"进行中"}'
# => {"id":"<WID>","code":"WP1","name":"需求调研", ...}
```

### Step 5 · 建任务（落到一个工作包 + 里程碑）
```bash
curl -s -X POST "{BASE}/api/tasks?project_id=$PID" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"code":"T1","title":"产出需求规格书","inputs":"访谈记录",
       "deliverables":"需求规格书.docx","acceptance":"评审通过",
       "human_owner":"H-001","ai_executor":"AI-PM-001",
       "priority":"P1","milestone_id":"<MID>","work_package_id":"<WID>"}'
# => {"id":"<TID>","code":"T1","title":"产出需求规格书","status":"待办", ...}
```

### Step 6 · 任务下拆子任务（第五层）
```bash
curl -s -X POST "{BASE}/api/wbs/subtasks?project_id=$PID" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"task_id":"<TID>","code":"ST-1","title":"整理干系人清单",
       "assignee":"AI-PM-001","priority":"P2"}'
# => {"id":"<SID>","code":"ST-1","title":"整理干系人清单","status":"待办", ...}
```

### Step 7 · 推进状态（状态机受约束，非法迁移返回 409）
```bash
# 子任务：待办 -> 进行中
curl -s -X POST "{BASE}/api/wbs/subtasks/<SID>/transition?project_id=$PID" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"进行中"}'

# 任务：待办 -> 进行中 -> 待评审（待评审/通过 需先登记证据）
curl -s -X POST "{BASE}/api/tasks/<TID>/transition?project_id=$PID" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"进行中"}'

curl -s -X POST "{BASE}/api/tasks/<TID>/evidence?project_id=$PID" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"paths":["03_日志/任务台账/T1_需求规格书.docx"],"summary":"已上传并自审"}'

curl -s -X POST "{BASE}/api/tasks/<TID>/transition?project_id=$PID" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"待评审"}'
```

### Step 8 · 查看整棵 WBS 树（一次拿全层级）
```bash
curl -s "{BASE}/api/wbs/tree?project_id=$PID" -H "Authorization: Bearer $TOKEN"
# => { "project_id": "...", "milestones": [ { "work_packages": [ { "tasks": [ { "sub_tasks": [...] } ] } ] } ] }
```

---

## 4. 给 AI 的"工具定义"建议（function calling / 插件 schema）

若把 PM-Collab 注册为 AI 工具，下面给出可直接复用的工具模板（以 JSON Schema 描述入参）。
AI 调用时把 `project_id` 作为公共参数透传即可。

```json
{
  "name": "pm_login",
  "description": "登录 PM-Collab 获取访问令牌",
  "parameters": {
    "type": "object",
    "properties": {
      "username": {"type": "string"},
      "password": {"type": "string"}
    },
    "required": ["username", "password"]
  }
}
```
```json
{
  "name": "pm_create_project",
  "description": "新建项目（自动初始化流程实例与4门禁）",
  "parameters": {
    "type": "object",
    "properties": {
      "code": {"type": "string", "description": "项目编号，全局唯一，如 PROJ-AI"},
      "name": {"type": "string"},
      "description": {"type": "string"},
      "owner": {"type": "string"}
    },
    "required": ["code", "name"]
  }
}
```
```json
{
  "name": "pm_create_milestone",
  "description": "在指定项目下新建里程碑",
  "parameters": {
    "type": "object",
    "properties": {
      "project_id": {"type": "string"},
      "code": {"type": "string"},
      "name": {"type": "string"},
      "status": {"type": "string", "enum": ["进行中","已完成","已归档"]},
      "owner": {"type": "string"}
    },
    "required": ["project_id","code","name"]
  }
}
```
```json
{
  "name": "pm_create_workpackage",
  "description": "在指定里程碑下新建工作包",
  "parameters": {
    "type": "object",
    "properties": {
      "project_id": {"type": "string"},
      "milestone_id": {"type": "string"},
      "code": {"type": "string"},
      "name": {"type": "string"}
    },
    "required": ["project_id","milestone_id","code","name"]
  }
}
```
```json
{
  "name": "pm_create_task",
  "description": "新建任务卡并关联到工作包/里程碑",
  "parameters": {
    "type": "object",
    "properties": {
      "project_id": {"type": "string"},
      "code": {"type": "string"},
      "title": {"type": "string"},
      "priority": {"type": "string", "enum": ["P0","P1","P2"]},
      "milestone_id": {"type": "string"},
      "work_package_id": {"type": "string"}
    },
    "required": ["project_id","code","title"]
  }
}
```
```json
{
  "name": "pm_create_subtask",
  "description": "在指定任务下拆一层子任务",
  "parameters": {
    "type": "object",
    "properties": {
      "project_id": {"type": "string"},
      "task_id": {"type": "string"},
      "code": {"type": "string"},
      "title": {"type": "string"},
      "assignee": {"type": "string"},
      "priority": {"type": "string", "enum": ["P0","P1","P2"]}
    },
    "required": ["project_id","task_id","code","title"]
  }
}
```
```json
{
  "name": "pm_transition_task",
  "description": "推进任务/子任务状态（受状态机约束）",
  "parameters": {
    "type": "object",
    "properties": {
      "project_id": {"type": "string"},
      "task_type": {"type": "string", "enum": ["task","subtask"]},
      "task_id": {"type": "string"},
      "target": {"type": "string", "enum": ["进行中","待评审","通过","返工","阻塞","关闭","取消"]}
    },
    "required": ["project_id","task_type","task_id","target"]
  }
}
```
```json
{
  "name": "pm_get_wbs_tree",
  "description": "获取整棵 WBS 树（里程碑→工作包→任务→子任务）",
  "parameters": {
    "type": "object",
    "properties": { "project_id": {"type": "string"} },
    "required": ["project_id"]
  }
}
```

> **最省事的方案**：让 AI 先 `GET {BASE}/openapi.json`（服务自带 OpenAPI 3 文档），
> 直接据此自动生成全部工具定义——字段、必填项、枚举都以该文件为准，无需手维护上面的 schema。

---

## 5. 完整接口索引（共 47 条，分组）

> 全部前缀 `{BASE}/api`。带 `*` 的需注意 `project_id` 隔离。权威定义见 `GET /openapi.json`。

**认证**
- `POST /auth/login` · `GET /auth/me`

**项目（WBS 根）\***
- `GET /projects` · `POST /projects` · `GET /projects/{project_id}`

**WBS 分解 \***
- 里程碑：`GET|POST /wbs/milestones` · `GET|PUT|DELETE /wbs/milestones/{mid}`
- 工作包：`GET|POST /wbs/workpackages`（支持 `?milestone_id=`）· `GET|PUT|DELETE /wbs/workpackages/{wid}`
- 子任务：`GET|POST /wbs/subtasks`（支持 `?task_id=`）· `GET|PUT|DELETE /wbs/subtasks/{sid}`
  · `POST /wbs/subtasks/{sid}/transition` · `POST /wbs/subtasks/{sid}/evidence`
- 树：`GET /wbs/tree`

**任务卡 \***
- `GET|POST /tasks` · `GET|PUT|DELETE /tasks/{task_id}`
- `POST /tasks/{task_id}/transition` · `POST /tasks/{task_id}/evidence`

**流程 / 门禁 \***
- `GET /process/instance` · `GET /process/gates` · `POST /process/gates/sign`
- `POST /process/advance` · `GET /process/checklist` · `POST /process/test-result`

**交接区 \***
- `GET /handoff/zones` · `POST /handoff/sync` · `POST /handoff/feed/{task_id}`
- `POST /handoff/{order_id}/transition` · `POST /handoff/{order_id}/close` · `POST /handoff/recycle/{order_id}`

**成员 / 角色**
- `GET /members` · `GET|PUT /members/{member_id}`
- `GET /roles` · `GET|PUT /roles/{role_id}`

**需求 / 文档 / 版本 / 检查点**
- `GET /requirements` · `GET /docs` · `POST /docs/{doc_id}/verify`
- `GET /versions` · `POST /versions/{version_id}/baseline` · `GET /libs/tree`

**报告 \***
- `GET /report/digest` · `GET /report/latest` · `GET /report/logs`
- `GET /report/metrics` · `POST /report/heartbeat`

---

## 6. 约束与最佳实践（AI 必须遵守）

1. **状态机不可越级**：任务/子任务状态只能按 `待办→进行中→待评审→通过→关闭`
   以及 `阻塞/取消/返工` 分支迁移；非法迁移返回 `409`。变更前可先 `GET /wbs/tree`
   或任务详情确认当前状态。
2. **证据前置**：把任务/子任务置为 `待评审` 或 `通过` 前，建议先 `POST .../evidence`
   登记产物路径（遵循"无证据不得置为通过"原则）。
3. **编号唯一**：项目 `code` 全局唯一；任务 / 里程碑 / 工作包 / 子任务 `code` 在**项目内唯一**（任务已由数据库复合唯一 `(project_id, code)` + API 查重双重保证，跨项目可复用相同编号）；重复会返回 `409`，AI 应先查重或采用时间戳编号（如 `T-<时间戳>`）。
   重复会返回 `409`，AI 应先查重或采用自增/时间戳编号（如 `ST-<时间戳>`）。
4. **层级依赖顺序**：先建里程碑 → 再建工作包（`milestone_id` 必填）→ 再建任务
   （`work_package_id`/`milestone_id` 可选但建议填）→ 任务建好后再拆子任务（`task_id` 必填）。
5. **多项目隔离**：凡带 `*` 的接口务必传 `?project_id`；遗漏会落到默认项目，造成数据错位。
6. **删除保护**：工作包下还有任务、里程碑下还有工作包时，删除会被拒绝（`409`）。
7. **审计留痕**：所有写操作都会自动写入审计日志（可在 `GET /report/logs` 查看），
   AI 的操作同样可追溯，符合"人机共用、双记"原则。

---

## 7. 给"豆包智能体"的具体接入提示

- **本机/私有化豆包**：直接把 `http://127.0.0.1:8731` 作为工具后端，按 §2–§3 注册 HTTP 工具即可。
- **云端豆包（豆包 API / 智能体平台）**：
  1. 在本机用任意语言（Python 最快）起一个 **MCP Server**，把 §4 的工具实现为 MCP 工具，
     内部转发到 `127.0.0.1:8731`；
  2. 把该 MCP Server 接入豆包（或任意支持 MCP 的客户端），云端豆包即可经 MCP 调用本机 PM-Collab，
     **服务无需暴露公网**；
  3. 或把 PM-Collab 部署到 CloudStudio / 云服务器，BASE_URL 指向公网地址，在豆包插件里注册 §5 的接口。
- **调试建议**：先用 `GET /openapi.json` 自检参数；用 `GET /report/logs` 复核 AI 的每一步操作。

---

## 8. 已知缺陷修复（2026-10-05）

测试发现并已修复三项缺陷（详见《PM-Collab AI功能测试报告_剧本1》§7、《PM-Collab AI功能测试报告_L1_V1.2》§4）：

- **DEF-01（中）任务编号唯一性作用域**：原先 `TaskCard.code` 为数据库全局唯一，导致跨项目复用同一编号被 `409` 拒绝。已改为 **`(project_id, code)` 复合唯一 + API 查重按 `project_id` 过滤**，即"项目内唯一、跨项目可复用"。
- **DEF-02（高）feed 交接单未继承 project_id**：`feed_task` 创建的交接单原先落入默认项目，按项目查询不可见。已修复为创建时显式传 `project_id=task.project_id`。
- **DEF-03（中）并发同编号提交竞态**：并发请求同时通过应用层查重后，`flush`/`commit` 触发 DB 唯一约束 `IntegrityError`，原先未捕获返回 `500`。已在 `create_task` 中捕获 `IntegrityError` 并映射为 `409`，回归用例 `test_n11`（4 线程并发同 code → 1×201 + 3×409）已全绿。

AI 调用时无需额外处理，上述约束已由服务端保证；仅需遵循 §6.3 的编号唯一与 §6.5 的项目隔离即可。

> 一句话总结给 AI：**"先登录拿 token，所有请求带 `Authorization: Bearer` 与
> `?project_id`，然后按 项目→里程碑→工作包→任务→子任务 的顺序调用 `/api/wbs/*` 与
> `/api/tasks/*`，状态迁移遵守状态机。"** 完整契约以 `GET {BASE}/openapi.json` 为准。
