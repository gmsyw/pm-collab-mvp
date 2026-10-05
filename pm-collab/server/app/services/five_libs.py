"""五库与交接区托管（E 域：目录由软件自动维护，T01）。

规则来源《文档组织方案 V1.0》§1 顶层五库 + 《通用方法 V1.1》§4 交接区 7 目录。
"""
from __future__ import annotations

from pathlib import Path

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
