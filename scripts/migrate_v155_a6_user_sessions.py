from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


PRODUCTION_DB = Path(
    "/home/admin/ai-tool/data/snapshots.db"
).resolve()


MIGRATION_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS v155_user_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER NOT NULL,

        session_key_hash TEXT NOT NULL UNIQUE
            CHECK (
                length(session_key_hash) = 64
                AND session_key_hash
                    NOT GLOB '*[^0-9a-f]*'
            ),

        session_version INTEGER NOT NULL
            CHECK (session_version >= 1),

        status TEXT NOT NULL DEFAULT 'active'
            CHECK (
                status IN (
                    'active',
                    'revoked',
                    'logged_out',
                    'expired'
                )
            ),

        created_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,

        revoked_at TEXT,

        revoke_reason TEXT NOT NULL DEFAULT '',

        revoked_by_user_id INTEGER,

        login_ip TEXT NOT NULL DEFAULT '',
        last_ip TEXT NOT NULL DEFAULT '',

        user_agent TEXT NOT NULL DEFAULT '',
        device_label TEXT NOT NULL DEFAULT '',

        FOREIGN KEY (user_id)
            REFERENCES v158_users(id)
            ON DELETE CASCADE,

        FOREIGN KEY (revoked_by_user_id)
            REFERENCES v158_users(id)
            ON DELETE SET NULL
    )
    """,

    """
    CREATE INDEX IF NOT EXISTS
        idx_v155_user_sessions_user_status_expiry
    ON v155_user_sessions (
        user_id,
        status,
        expires_at
    )
    """,

    """
    CREATE INDEX IF NOT EXISTS
        idx_v155_user_sessions_user_last_seen
    ON v155_user_sessions (
        user_id,
        last_seen_at
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS
        v155_user_session_policies (
            user_id INTEGER PRIMARY KEY,

            max_active_sessions INTEGER NOT NULL
                CHECK (
                    max_active_sessions
                    BETWEEN 1 AND 10
                ),

            updated_at TEXT NOT NULL,

            updated_by_user_id INTEGER,

            FOREIGN KEY (user_id)
                REFERENCES v158_users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (updated_by_user_id)
                REFERENCES v158_users(id)
                ON DELETE SET NULL
        )
    """,
)


def apply_migration(
    conn: sqlite3.Connection,
) -> None:
    if conn.in_transaction:
        raise RuntimeError(
            "migration requires explicit "
            "transaction ownership"
        )

    conn.execute(
        "PRAGMA foreign_keys=ON"
    )

    foreign_keys = int(
        conn.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]
    )

    if foreign_keys != 1:
        raise RuntimeError(
            "foreign_keys must be enabled"
        )

    conn.execute(
        "BEGIN IMMEDIATE"
    )

    try:
        for statement in MIGRATION_STATEMENTS:
            conn.execute(statement)

        conn.commit()

    except Exception:
        if conn.in_transaction:
            conn.rollback()

        raise


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--db",
        required=True,
    )

    args = parser.parse_args()

    db_path = (
        Path(args.db)
        .expanduser()
        .resolve()
    )

    if db_path == PRODUCTION_DB:
        parser.error(
            "production database execution "
            "is not authorized during A6-A3"
        )

    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        str(db_path),
        timeout=15,
    )

    try:
        apply_migration(conn)

        print(
            "A6_ISOLATED_MIGRATION=PASS"
        )

        print(
            "DATABASE="
            + str(db_path)
        )

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
