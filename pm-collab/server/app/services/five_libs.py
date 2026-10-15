"""五库与交接区托管（E 域：目录由软件自动维护，T01）。

规则来源《文档组织方案 V1.0》§1 顶层五库 + 《通用方法 V1.1》§4 交接区 7 目录。
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings

# 五库
LIBRARIES = (
    "01_项目库",
    "02_交付物",
    "03_日志",
    "04_模板",
    "05_版本库",
)

LIBRARY_SUBDIRS: dict[str, tuple[str, ...]] = {
    "01_项目库": ("项目章程", "成员名册与角色卡", "需求基线", "计划与里程碑", "变更单", "评审记录单"),
    "02_交付物": ("01_需求", "02_设计", "03_验收", "04_测试", "代码"),
    "03_日志": ("交互日志", "任务台账", "问题与风险台账", "日报周报"),
    "04_模板": ("角色卡", "设计文档", "评审记录单", "测试记录单", "版本台账"),
    "05_版本库": ("发布日志", "archive"),
}

# 交接区 7 项（6 目录 + 交接单.json）
HANDOFF_ZONES = ("派单", "回执", "完成", "评审输入", "评审输出", "卡点")
HANDOFF_LEDGER = "交接单.json"


def ensure_libraries() -> list[Path]:
    """确保五库 + 交接区（含 7 目录与交接单）存在；缺失即自动创建。"""
    created: list[Path] = []

    def _mk(path: Path) -> None:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)

    _mk(settings.data_dir)
    for lib in LIBRARIES:
        lib_dir = settings.data_dir / lib
        _mk(lib_dir)
        for sub in LIBRARY_SUBDIRS.get(lib, ()):
            _mk(lib_dir / sub)
    for zone in HANDOFF_ZONES:
        _mk(settings.handoff_dir / zone)
    _mk(settings.handoff_dir)
    ledger = settings.handoff_dir / HANDOFF_LEDGER
    if not ledger.exists():
        ledger.write_text(
            '{\n  "project": "PM-Collab",\n  "updated_at": "",\n  "orders": []\n}\n',
            encoding="utf-8",
        )
        created.append(ledger)
    return created


def zone_path(zone: str) -> Path:
    return settings.handoff_dir / zone


def list_zone_files() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for zone in HANDOFF_ZONES:
        p = zone_path(zone)
        if not p.exists():
            out[zone] = []
            continue
        out[zone] = sorted(f.name for f in p.iterdir() if f.is_file())
    return out


# ---------------- 按项目隔离的目录结构 ----------------
# 每个项目在 data/projects/<项目编号>/ 下拥有独立五库 + 交接区，资料互不串味。
# 注意：PROJECTS_ROOT 必须动态计算（依赖 settings.data_dir），不能在模块加载时固化，
# 否则测试用临时 data_dir 时路径仍指向真实目录，导致测试隔离失效。


def projects_root() -> Path:
    return settings.data_dir / "projects"


def safe_segment(name: str) -> str:
    """把项目编号/名称清洗为合法目录名（保留中文，剔除文件系统禁用字符）。"""
    s = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip().strip(".")
    return s[:80] or "未命名"


def project_dir(code: str) -> Path:
    return projects_root() / safe_segment(code)


def project_code_by_id(db: Session, project_id: str) -> str:
    """按项目 id 取编号（用于目录命名）；取不到时回退全局名。"""
    from ..models import Project

    p = db.get(Project, project_id)
    return p.code if p else "PM-Collab"


def ensure_project_structure(code: str) -> Path:
    """为某项目建立独立目录：五库（含子目录）+ 交接区（7 目录 + 交接单.json）。

    幂等；同时保留全局模板库（04_模板）供共享。
    """
    ensure_libraries()  # 保留全局模板库等共享资产
    root = project_dir(code)
    for lib in LIBRARIES:
        d = root / lib
        d.mkdir(parents=True, exist_ok=True)
        for sub in LIBRARY_SUBDIRS.get(lib, ()):
            (d / sub).mkdir(parents=True, exist_ok=True)
    for zone in HANDOFF_ZONES:
        (root / "交接区" / zone).mkdir(parents=True, exist_ok=True)
    ledger = root / "交接区" / HANDOFF_LEDGER
    if not ledger.exists():
        ledger.write_text(
            '{\n  "project": "%s",\n  "updated_at": "",\n  "orders": []\n}\n' % code,
            encoding="utf-8",
        )
    return root


def project_lib_path(code: str, library: str, sub: str = "") -> Path:
    p = project_dir(code) / library
    if sub:
        p = p / sub
    return p


def project_zone_path(code: str, zone: str) -> Path:
    return project_dir(code) / "交接区" / zone


def project_ledger_path(code: str) -> Path:
    return project_dir(code) / "交接区" / HANDOFF_LEDGER


def list_project_zone_files(code: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for zone in HANDOFF_ZONES:
        p = project_zone_path(code, zone)
        if not p.exists():
            out[zone] = []
            continue
        out[zone] = sorted(f.name for f in p.iterdir() if f.is_file())
    return out


def ensure_all_project_dirs(db: Session) -> int:
    """启动期补齐所有项目（含既有 23 个）的独立目录；返回已确保数量。"""
    from ..models import Project

    n = 0
    for proj in db.query(Project).all():
        ensure_project_structure(proj.code)
        n += 1
    return n
