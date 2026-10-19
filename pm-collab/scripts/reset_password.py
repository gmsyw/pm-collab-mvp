"""CLI：本机重置 admin 口令（OSS-07 / UR-7）。

仅在本机命令行执行，不暴露任何 API。重置后所有现有登录会话（JWT）一并吊销。
复用既有 db / config / security / audit，不重复造轮子。
"""
from __future__ import annotations

import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保 pm-collab 根目录在 sys.path（无论以何种方式调用），以便导入 server.app.*。
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy.orm import Session  # noqa: E402

from server.app.audit import write_log  # noqa: E402
from server.app.config import settings  # noqa: E402
from server.app.db import SessionLocal  # noqa: E402
from server.app.models import Member  # noqa: E402
from server.app.security import hash_password  # noqa: E402


def reset_admin_password(db: Session) -> str:
    """重置 admin（settings.bootstrap_username）口令为随机值，并吊销旧会话。

    返回新口令字符串，仅由调用方在控制台一次性打印；不落库、不落日志。
    """
    member = db.query(Member).filter(Member.username == settings.bootstrap_username).first()
    if member is None:
        # 与 auth.ensure_bootstrap 口径一致：admin 不存在则创建（H-001 / Dr Ming）。
        member = Member(
            code="H-001",
            name="Dr Ming（PO/PM/TL）",
            member_type="人类",
            status="在岗",
            username=settings.bootstrap_username,
        )
        db.add(member)
    new_password = secrets.token_urlsafe(12)  # >=12 字符，零硬编码字面量
    member.password_hash = hash_password(new_password)
    # 吊销旧会话：与 /api/auth/change-password 口径一致（token_valid_from 无状态吊销）。
    member.token_valid_from = datetime.now(tz=timezone.utc)
    write_log(
        db,
        actor=member.name,
        action="重置密码",
        change="通过 CLI 重置 admin 密码，旧会话已失效（新口令仅控制台一次性显示）",
    )
    db.commit()
    return new_password


def main() -> int:
    print("警告：此操作将重置 admin 密码并使所有现有登录失效。")
    answer = input("确认继续？请输入 y 继续：").strip().lower()
    if answer != "y":
        print("已取消，未做任何修改。")
        return 1
    db = SessionLocal()
    try:
        new_password = reset_admin_password(db)
    finally:
        db.close()
    print("admin 新密码（仅显示一次，请妥善保存，不会再次显示）：")
    print(new_password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
