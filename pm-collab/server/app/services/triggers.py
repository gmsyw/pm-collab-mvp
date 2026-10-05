"""追加式日志的库层强制：触发器 + REVOKE（需求书 §5.2；T06）。

SQLite 形态用 BEFORE UPDATE/DELETE 触发器 RAISE(ABORT) 达成同等等价约束；
PostgreSQL 形态另加 pgcrypto 扩展与 REVOKE，双写皆可判决命中。
"""
from __future__ import annotations

SQLITE_TRIGGERS = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_append_logs_no_update
    BEFORE UPDATE ON append_logs
    BEGIN
      SELECT RAISE(ABORT, '追加式日志不可改：禁止 UPDATE');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_append_logs_no_delete
    BEFORE DELETE ON append_logs
    BEGIN
      SELECT RAISE(ABORT, '追加式日志不可删：禁止 DELETE');
    END
    """,
)

POSTGRES_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    """
    CREATE OR REPLACE FUNCTION prevent_append_log_modification() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION '追加式日志不可改删：append_logs 仅允许 INSERT';
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_append_logs_lock'
      ) THEN
        CREATE TRIGGER trg_append_logs_lock
        BEFORE UPDATE OR DELETE ON append_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_append_log_modification();
      END IF;
    END $$
    """,
    "REVOKE UPDATE, DELETE ON append_logs FROM PUBLIC",
)


def statements_for(dialect: str) -> tuple[str, ...]:
    if dialect == "sqlite":
        return SQLITE_TRIGGERS
    if dialect == "postgresql":
        return POSTGRES_STATEMENTS
    return ()
