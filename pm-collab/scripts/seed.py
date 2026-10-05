"""种子数据导入 CLI：python scripts/seed.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from server.app.db import SessionLocal  # noqa: E402
from server.app.services.db_bootstrap import init_db  # noqa: E402
from server.seed.seed_all import seed_all  # noqa: E402


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        counts = seed_all(db)
        total_mvp = None
        from server.app.models import RequirementItem

        total_mvp = db.query(RequirementItem).filter(RequirementItem.in_mvp.is_(True)).count()
        print("[seed] 导入完成：")
        for k, v in counts.items():
            print(f"  - {k}: 新增 {v}")
        print(f"  - MVP 范围内需求条目合计：{total_mvp}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
