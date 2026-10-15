"""种子数据：需求条目（T07）+ 角色卡/名册 + MVP 任务卡 T01–T25。

幂等：按编号去重，可重复执行。
数据来源：《项目管理AI（PM-AI）需求规格书 V1.0》《PM-Collab MVP 任务分解 V1.0》。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from server.app.models import (
    DEFAULT_PROJECT_ID,
    Member,
    Milestone,
    RequirementItem,
    RoleCard,
    SubTask,
    TaskCard,
    WorkPackage,
)
from server.app.security import hash_password
from server.app.services.projects import ensure_default_project

# ---------------- 角色卡（8 字段，需求书 §2.4） ----------------
ROLES = [
    dict(code="ROLE-PO", role_type="人类角色", duty="需求拍板、产品方向与优先级决策",
         negative_list="不代做技术选型", permission_level="L4",
         data_boundary="项目全量数据（只读+审批）", reports_to="-", downgrade_plan="由 PM/TL 暂代，报项目负责人备案"),
    dict(code="ROLE-PM", role_type="人类角色", duty="计划与里程碑、阻塞处置、对外协调",
         negative_list="不绕过门禁放行", permission_level="L4",
         data_boundary="项目全量数据", reports_to="PO", downgrade_plan="由 PO 接管"),
    dict(code="ROLE-TL", role_type="人类角色", duty="技术方案裁决、设计/代码评审终审",
         negative_list="不代签验收", permission_level="L4",
         data_boundary="设计与代码库", reports_to="PO", downgrade_plan="引入外部评审角色复核"),
    dict(code="ROLE-PM-AI", role_type="AI角色", duty="任务分解/指派、进度扫描、回收归档、门禁判定、告警与报表",
         negative_list="不代签验收；不编造凭据；不改已签基线；不做技术决策", permission_level="L3",
         data_boundary="仅经服务层 API 读写；禁止直连数据库", reports_to="PM",
         downgrade_plan="失效期间禁止 L3 操作，降级为 L1 只读，由 PM 接管扫描与归档"),
    dict(code="ROLE-ARCH-AI", role_type="AI角色", duty="顶层设计、接口基线、集成验证",
         negative_list="不越权修改基线外的实现", permission_level="L2",
         data_boundary="设计文档区与接口规格，只读代码", reports_to="TL",
         downgrade_plan="由 TL 与外部评审角色接管设计"),
    dict(code="ROLE-DEV-AI", role_type="AI角色", duty="模块设计、开发实现、单元测试",
         negative_list="不得自测即宣告通过；测试独立性隔离", permission_level="L3",
         data_boundary="server/web 源码与单测目录", reports_to="TL",
         downgrade_plan="拆分模块交由其他实例或外部角色接管"),
    dict(code="ROLE-EXEC-AI", role_type="AI角色", duty="文档落地、批量文件操作、检索等执行任务",
         negative_list="不受理无任务卡指令", permission_level="L3",
         data_boundary="五库目录与交接区", reports_to="PM-AI",
         downgrade_plan="由 PM-AI 直接执行或转 DEV-AI"),
    dict(code="ROLE-QA-AI", role_type="AI角色", duty="集成测试、回归测试、标准测试报告、缺陷回归验证",
         negative_list="不得复核自身开发产出；测试者须为独立实例", permission_level="L3",
         data_boundary="tests/ 与测试报告目录，只读源码", reports_to="PM",
         downgrade_plan="引入外部角色独立复核关键模块"),
    dict(code="ROLE-REVIEW-AI", role_type="AI角色", duty="设计/代码评审初审、评审意见整理（阻塞/建议/疑问）",
         negative_list="不得代替 TL 终审签字", permission_level="L2",
         data_boundary="评审输入/输出目录与设计文档（只读）", reports_to="TL",
         downgrade_plan="由 TL 直接终审"),
]

MEMBERS = [
    dict(code="H-001", name="Dr Ming（PO/PM/TL）", member_type="人类", reports_to="", username="admin"),
    dict(code="AI-PM-001", name="项目管理 AI（PM-AI）", member_type="AI", reports_to="H-001"),
    dict(code="AI-ARCH-001", name="顶层设计产品集成 AI", member_type="AI", reports_to="H-001"),
    dict(code="AI-DEV-001", name="设计开发测试 AI", member_type="AI", reports_to="H-001"),
    dict(code="AI-EXEC-001", name="执行类 Agent", member_type="AI", reports_to="H-001"),
    dict(code="AI-QA-001", name="QA-AI（独立实例）", member_type="AI", reports_to="H-001"),
    dict(code="AI-REVIEW-001", name="Review-AI（独立实例）", member_type="AI", reports_to="H-001"),
]

# ---------------- 需求条目（需求规格书 V1.0 全章节条目化） ----------------
REQUIREMENTS = [
    # §1 定位与边界
    ("R-1.1", "1.1", "PM-AI 是项目组正式成员（AI Agent），并承担项目管家职责", "P0", True),
    ("R-1.2", "1.2", "负责进度跟踪、分派（限 L3 内）、归档、留痕、门禁判定与告警；不做技术决策", "P0", True),
    ("R-1.3", "1.3", "自主决策范围：状态扫描、例行提醒告警、版本归档、L1/L2 查询统计与方案起草", "P1", True),
    ("R-1.4", "1.4", "人类审批范围：4 门禁签字、L3 人工确认、L4 备份+双人审批、一切变更批准", "P0", True),
    ("R-1.5", "1.5", "负面清单：不代签验收、不编造凭据、不改已签基线、不越权限、不代替人类技术决策", "P0", True),
    ("R-1.6", "1.6", "设计原则：文档先行、阶段签署、持续评审链、全程留痕、版本不覆盖、最小影响、证据驱动", "P0", True),
    # §2 组织与角色
    ("R-2.1", "2.1", "人类与 AI 角色统一建档、统一编号，形成成员名册与授权记录", "P0", True),
    ("R-2.2", "2.2", "人类角色 PO/PM/TL 为决策与审批主体", "P0", True),
    ("R-2.3", "2.3", "AI 角色共 6 个：项目管理/顶层设计产品集成/设计开发测试/执行类/QA/Review", "P0", True),
    ("R-2.4", "2.4", "角色卡 8 字段：ID/类型/职责/负面清单/权限等级/数据与工具边界/汇报对象/降级预案", "P0", True),
    ("R-2.5", "2.5", "权限分级 L1–L4：只读/建议/执行需确认/受限", "P1", True),
    ("R-2.6", "2.6", "责任分离与降级：批准与验收必须落人，AI 失效按角色卡降级预案接管", "P0", False),
    ("R-2.7", "2.7", "编制变更（增删角色、升降权限）须走变更流程并由项目负责人批准", "P2", False),
    # §3 流程与门禁
    ("R-3.1", "3.1", "8 阶段不可跳过流水线：需求录入→设计→设计评审→开发→代码评审→测试→验收→归档", "P0", True),
    ("R-3.2", "3.2", "每阶段定义准入/准出条件，PM-AI 检查并放行，条件不满足不得进入下一阶段", "P0", True),
    ("R-3.3", "3.3", "4 个质量门禁必须人类签字：需求评审/设计评审/代码评审/验收", "P0", True),
    ("R-3.4", "3.4", "阶段准出示例：开发需单测通过且覆盖率≥80%，测试需集成回归通过且缺陷关闭", "P0", True),
    # §4 任务
    ("R-4.1", "4.1", "分解层级：项目→里程碑→工作包→任务", "P0", True),
    ("R-4.2", "4.2", "任务卡 14 字段：ID/目标/输入/交付物及路径/验收标准/人-A/AI-R/依赖/起止/优先级/状态/证据/完成摘要", "P0", True),
    ("R-4.3", "4.3", "任务状态机：待办→进行中→待评审→通过/返工→关闭；另有阻塞、取消", "P0", True),
    ("R-4.4", "4.4", "按角色卡能力与权限匹配派单，禁止越权派单；PM-AI 扫描并更新看板", "P1", True),
    ("R-4.5", "4.5", "派单入口：手机短指令、命令文件；AI 必须先回执复述，歧义必反问", "P2", False),
    ("R-4.6", "4.6", "阻塞须填原因与责任方并进问题台账；阻塞超 24 小时自动告警 PM", "P1", True),
    ("R-4.7", "4.7", "每个任务完成后必须有完成摘要记录", "P0", True),
    # §5 进度与留痕
    ("R-5.1", "5.1", "PM-AI 每次激活按优先级扫描：任务状态→阻塞告警→门禁审批→版本归档→成员查询", "P1", True),
    ("R-5.2", "5.2", "追加式日志：完成即记录，只增不改、不可删除，7 字段", "P0", True),
    ("R-5.3", "5.3", "证据链：无证据不得置为通过，任一结论可回溯到交互+证据+确认人", "P0", True),
    ("R-5.4", "5.4", "报表：里程碑看板、偏差/燃尽、周报、逾期清单", "P1", True),
    ("R-5.5", "5.5", "人机对账：AI 侧完成项与人工反馈逐日核对，差异入台账", "P2", False),
    # §6 文档先行
    ("R-6.1", "6.1", "文档模板四类 SRS/TDD/API/DB；建档须唯一编号+版本号+责任人", "P1", True),
    ("R-6.2", "6.2", "命名规则：项目-类型-名称-V主.次.修订.扩展名，状态不入文件名", "P1", True),
    ("R-6.3", "6.3", "评审流程：草稿→待评审→评审中→通过/返工→基线化；未通过不得开发", "P0", True),
    ("R-6.4", "6.4", "评审分级：Review-AI 初审 + TL 终审；意见分阻塞/建议/疑问三级", "P1", False),
    ("R-6.5", "6.5", "评审记录独立存档", "P2", True),
    # §7 测试驱动
    ("R-7.1", "7.1", "单元测试必须编写，覆盖率≥80%", "P0", True),
    ("R-7.2", "7.2", "QA-AI 执行集成测试与回归测试，输出标准测试报告", "P0", True),
    ("R-7.3", "7.3", "测试独立性：测试者不得为唯一开发者，否则须独立复核", "P0", True),
    ("R-7.4", "7.4", "缺陷登记并回归，未通过不得关闭任务", "P1", False),
    ("R-7.5", "7.5", "测试门槛：测试不通过不得进入验收", "P0", True),
    ("R-7.6", "7.6", "追溯矩阵：需求→设计→实现→用例→结果，双向可查", "P1", True),
    # §8 版本
    ("R-8.1", "8.1", "版本号 X.Y.Z 三位；引用必须带版本号，禁止使用最新版", "P1", True),
    ("R-8.2", "8.2", "不覆盖原则：每次更新生成新版本，旧版本永久保留", "P0", True),
    ("R-8.3", "8.3", "版本台账字段：版本号/日期/执行者/变更摘要/变更单/评审状态/路径/哈希", "P0", True),
    ("R-8.4", "8.4", "仅评审通过版本可作基线；代码 tag 与文档版本对齐", "P1", True),
    ("R-8.5", "8.5", "每次发布记入版本发布日志", "P1", True),
    # §9 人机交互
    ("R-9.1", "9.1", "交互即事件：渠道/指令原文/AI 理解/执行动作/结果/人工确认/关联任务", "P2", False),
    ("R-9.2", "9.2", "AI 不主动发起对话（告警/通知除外）", "P2", True),
    ("R-9.3", "9.3", "交互闭环：每次交互必须有明确闭环，不得悬置", "P1", True),
    ("R-9.4", "9.4", "越权防线：参数缺失只问不猜，不得推定关键参数", "P1", True),
    ("R-9.5", "9.5", "中止与回滚：可中止并回退至上一已确认状态，且留痕", "P2", False),
    ("R-9.6", "9.6", "全程审计：任一交互、结论可回溯到交互+证据+确认人", "P1", True),
    # §10 变更与风险
    ("R-10.1", "10.1", "范围/时间/资源/接口/基线变更须出变更单，影响分析后由人批准", "P2", False),
    ("R-10.2", "10.2", "风险与问题台账：定级、责任人、关闭标准；到期顺延项须显式二次登记", "P2", False),
    # §11 度量与反馈
    ("R-11.1", "11.1", "度量四指标：按期率、返工率、AI 产出采纳率、评审问题关闭率", "P1", True),
    ("R-11.2", "11.2", "通知：每日摘要、周报、逾期提醒推送", "P1", True),
    ("R-11.3", "11.3", "知识沉淀：踩坑与方法入库复用", "P2", False),
    ("R-11.4", "11.4", "日常工作清单：任务状态→阻塞告警→门禁审批→版本归档→成员查询", "P1", True),
    # §12 数据与运行
    ("R-12.1", "12.1", "目录规范：项目库/交付物/日志/模板/版本库分离", "P0", True),
    ("R-12.2", "12.2", "非功能要求：可追溯、可审计、本机原生运行、权限隔离、定期备份", "P1", True),
    # §13 交付物
    ("R-13.1", "13.1", "模板交付：角色卡、设计文档、评审记录单、测试记录单、版本台账五套模板", "P1", True),
    ("R-13.2", "13.2", "评审确认项：实施范围/AI 权限上限 L3/记录载体/门禁强度/测试独立性/版本号规则", "P1", True),
    ("R-13.3", "13.3", "落地路线：MVP → 状态机与证据链 → 分级审批与审计 → 变更与知识沉淀", "P0", True),
]

# ---------------- MVP 任务卡 T01–T25 ----------------
TASKS = [
    ("T01", "初始化项目骨架与五库", "WP0 项目准备", "pm-collab 骨架 + data 五库 + 交接区 7 目录",
     "目录结构符合《文档组织方案》；交接区含 6 子目录与交接单.json", "H", "执行类 Agent", [], "P0"),
    ("T02", "开发环境搭建", "WP0 项目准备", "虚拟环境与依赖清单 + 环境配置说明",
     "服务可启动、数据库可连接、迁移命令可执行", "H", "执行类 Agent", ["T01"], "P0"),
    ("T03", "CI/测试骨架", "WP0 项目准备", "pytest 配置与测试套件",
     "测试命令通过、覆盖率采集可用", "H", "设计开发测试 AI", ["T02"], "P1"),
    ("T04", "数据模型落地", "WP1 数据模型与迁移", "10 表 ORM 模型与字段约束",
     "与设计大纲 §4 一致", "H", "顶层设计产品集成 AI", ["T02"], "P0"),
    ("T05", "Alembic 迁移脚本", "WP1 数据模型与迁移", "初版迁移脚本",
     "空库可迁移至最新；降级可回滚", "H", "设计开发测试 AI", ["T04"], "P0"),
    ("T06", "追加日志触发器", "WP1 数据模型与迁移", "触发器 + REVOKE 约束",
     "UPDATE/DELETE 被数据库拒绝；插入即记录", "H", "设计开发测试 AI", ["T05"], "P0"),
    ("T07", "需求条目导入", "WP1 数据模型与迁移", "需求条目库种子数据",
     "覆盖需求规格书全部条目；可追溯", "H", "PM-AI", ["T04"], "P1"),
    ("T08", "认证与用户基础", "WP2 服务层 API", "单用户登录 + JWT",
     "登录可用；未授权请求被拒", "H", "设计开发测试 AI", ["T03"], "P0"),
    ("T09", "名册/角色卡 API", "WP2 服务层 API", "成员与角色卡 CRUD",
     "API 测试通过；非法字段被拒", "H", "设计开发测试 AI", ["T08"], "P0"),
    ("T10", "任务卡 API", "WP2 服务层 API", "任务卡 CRUD + 14 字段 + 状态机",
     "非法状态迁移被拒；阻塞/取消可用", "H", "设计开发测试 AI", ["T08"], "P0"),
    ("T11", "流程引擎骨架", "WP2 服务层 API", "8 阶段状态机 + 门禁记录",
     "阶段流转受控；无门禁签字不放行", "H", "顶层设计产品集成 AI", ["T10"], "P0"),
    ("T12", "文档条目/版本台账 API", "WP2 服务层 API", "登记 + 哈希校验",
     "哈希不匹配即告警；台账只增不改", "H", "设计开发测试 AI", ["T09"], "P1"),
    ("T13", "交接区监听", "WP3 交接总线", "watchdog 监听服务",
     "新文件/变更事件可捕获并触发回调", "H", "设计开发测试 AI", ["T02"], "P0"),
    ("T14", "交接单 JSON 同步", "WP3 交接总线", "文件与库双向同步",
     "4 态状态机完整流转；双写一致", "H", "设计开发测试 AI", ["T10", "T13"], "P0"),
    ("T15", "投喂/回收助手", "WP3 交接总线", "投喂与回收归档功能",
     "端到端：投喂→角色回写→回收→台账", "H", "设计开发测试 AI", ["T14", "T19"], "P1"),
    ("T16", "卡点信号生成与队列", "WP3 交接总线", "卡点 6 字段 + 队列接口",
     "卡点可入队、可标记处理", "H", "设计开发测试 AI", ["T11"], "P1"),
    ("T17", "前端骨架", "WP4 前端", "Vue3 + Vite + Element Plus + 路由布局",
     "开发服务器可运行、页面路由完整", "H", "设计开发测试 AI", ["T03"], "P0"),
    ("T18", "看板页", "WP4 前端", "任务/阶段/里程碑总览 + ECharts",
     "数据来自 API；图表渲染正确", "H", "设计开发测试 AI", ["T17", "T11"], "P0"),
    ("T19", "任务卡页", "WP4 前端", "创建/编辑/状态流转操作",
     "CRUD 闭环；状态迁移与后端一致", "H", "设计开发测试 AI", ["T17", "T10"], "P0"),
    ("T20", "交接区与卡点视图", "WP4 前端", "文件列表 + 卡点队列（WebSocket 实时）",
     "新卡点实时出现", "H", "设计开发测试 AI", ["T17", "T16"], "P1"),
    ("T21", "摘要生成", "WP5 每日摘要", "APScheduler 定时任务 + 汇总逻辑",
     "每日定时输出；数据与库一致", "H", "PM-AI", ["T11"], "P0"),
    ("T22", "摘要推送", "WP5 每日摘要", "本地通知/日志输出 + 可选 webhook",
     "推送成功并留痕", "H", "PM-AI", ["T21"], "P1"),
    ("T23", "集成测试与回归", "WP6 测试与验收", "端到端用例",
     "全部通过；单测覆盖率≥80%", "H", "QA-AI", ["T11", "T22"], "P0"),
    ("T24", "验收清单与门禁④", "WP6 测试与验收", "对照范围逐项核验",
     "全部项通过；H 签字", "H", "PM-AI", ["T23"], "P0"),
    ("T25", "归档与基线", "WP7 归档与基线", "版本台账、发布日志、入 05_版本库",
     "台账/日志登记完整；旧版本保留", "H", "PM-AI", ["T24"], "P1"),
]

SOURCE_DOC = "需求规格书 V1.0"


def seed_all(db: Session, default_password: str = "") -> dict[str, int]:
    counts = {"roles": 0, "members": 0, "requirements": 0, "tasks": 0}

    for r in ROLES:
        if db.query(RoleCard).filter(RoleCard.code == r["code"]).first():
            continue
        db.add(RoleCard(**r))
        counts["roles"] += 1

    for m in MEMBERS:
        exists = db.query(Member).filter(Member.code == m["code"]).first()
        if exists:
            continue
        data = dict(m)
        if data.get("username"):
            data["password_hash"] = hash_password(default_password)
        db.add(Member(**data))
        counts["members"] += 1

    for code, section, content, priority, in_mvp in REQUIREMENTS:
        if db.query(RequirementItem).filter(RequirementItem.code == code).first():
            continue
        db.add(RequirementItem(
            code=code, section=section, content=content, priority=priority,
            in_mvp=in_mvp, review_status="评审通过" if in_mvp else "待评审",
            source_doc=SOURCE_DOC, trace_links=[],
        ))
        counts["requirements"] += 1

    # ---------------- WBS 骨架：里程碑 + 工作包（需求书 §4.1） ----------------
    milestone = db.query(Milestone).filter(
        Milestone.project_id == DEFAULT_PROJECT_ID, Milestone.code == "MVP"
    ).first()
    if milestone is None:
        milestone = Milestone(
            project_id=DEFAULT_PROJECT_ID, code="MVP", name="MVP",
            description="PM-Collab MVP 里程碑（首跑全流程）", status="进行中",
        )
        db.add(milestone)
        db.flush()
        counts["milestones"] = 1

    # 工作包字典：wp 展示名 → WorkPackage 行（幂等）
    wp_map: dict[str, WorkPackage] = {}
    for _c, _t, wp, *_ in TASKS:
        if not wp or wp in wp_map:
            continue
        code = wp.split(" ", 1)[0]
        existing = db.query(WorkPackage).filter(
            WorkPackage.project_id == DEFAULT_PROJECT_ID, WorkPackage.code == code
        ).first()
        if existing is None:
            existing = WorkPackage(
                project_id=DEFAULT_PROJECT_ID, milestone_id=milestone.id,
                code=code, name=wp, status="进行中",
            )
            db.add(existing)
            db.flush()
            counts["work_packages"] = counts.get("work_packages", 0) + 1
        wp_map[wp] = existing

    for code, title, wp, deliverables, acceptance, human, ai, deps, priority in TASKS:
        if db.query(TaskCard).filter(TaskCard.code == code).first():
            continue
        wp_row = wp_map.get(wp)
        db.add(TaskCard(
            code=code, title=title, goal=title, deliverables=deliverables,
            acceptance=acceptance, human_owner=human, ai_executor=ai,
            dependencies=deps, priority=priority, status="待办",
            milestone="MVP", work_package=wp or "",
            milestone_id=milestone.id,
            work_package_id=wp_row.id if wp_row else None,
        ))
        counts["tasks"] += 1

    ensure_default_project(db)
    db.commit()
    return counts
