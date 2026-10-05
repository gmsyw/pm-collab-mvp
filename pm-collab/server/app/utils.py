"""通用工具：文件哈希、命名校验、时间格式。"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

# 命名格式：项目-类型-名称-V主.次.修订.扩展名（文档组织方案 §4.1）
NAME_PATTERN = re.compile(r"^.+-.+-.+-V\d+\.\d+\.\d+\.[A-Za-z0-9]+$")

# 类型词表（文档组织方案 §4.2）
TYPE_WORDS = (
    "章程", "名册", "角色卡", "需求基线", "计划", "变更单", "设计文档",
    "测试报告", "验收记录", "交互日志", "任务台账", "问题台账", "日报",
    "周报", "模板", "版本台账", "发布日志",
)


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_doc_name(filename: str) -> tuple[bool, str]:
    """校验文档命名是否符合《文档组织方案》§4；返回 (是否通过, 说明)。"""
    if not NAME_PATTERN.match(filename):
        return False, "命名格式应为：项目-类型-名称-V主.次.修订.扩展名（状态不入文件名）"
    # 末段为版本号，倒数第二段为名称，倒数第三段为类型词
    parts = filename.split("-")
    type_word = parts[-3] if len(parts) >= 3 else ""
    if type_word not in TYPE_WORDS:
        return False, f"类型词「{type_word}」不在类型词表内：{list(TYPE_WORDS)}"
    return True, "命名合规"


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def ensure_aware(dt: datetime | None) -> datetime | None:
    """SQLite 驱动返回 naive datetime，统一补 UTC 时区以便运算。"""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def today_str() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
