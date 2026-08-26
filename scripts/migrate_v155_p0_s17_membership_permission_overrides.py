from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


TABLE_NAME = (
    "v155_membership_permission_overrides"
)

INDEX_NAME = (
    "idx_v155_membership_permission_overrides_permission"
)


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS
v155_membership_permission_overrides (
    membership_id INTEGER NOT NULL,

    permission_id INTEGER NOT NULL,

    effect TEXT NOT NULL
        CHECK (
            effect IN (
                'grant',
                'deny'
            )
        ),

    created_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    updated_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    PRIMARY KEY (
        membership_id,
        permission_id
    ),

    FOREIGN KEY (
        membership_id
    )
    REFERENCES v155_workspace_members(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,

    FOREIGN KEY (
        permission_id
    )
    REFERENCES v155_permissions(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE
)
"""


CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS
idx_v155_membership_permission_overrides_permission
ON v155_membership_permission_overrides(
    permission_id
)
"""


def _resolve_database_path(
    value: str,
) -> Path:
    path = Path(
        value
    ).expanduser().resolve()

    if not path.is_file():
        raise ValueError(
            f"database does not exist: {path}"
        )

    return path


def _required_base_tables_present(
    conn: sqlite3.Connection,
) -> None:
    required = {
        "v155_workspace_members",
        "v155_permissions",
    }

    present = {
        str(row[0])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """
        )
    }

    missing = sorted(
        required - present
    )

    if missing:
        raise RuntimeError(
            "missing required tables: "
            + ",".join(missing)
        )


def _table_exists(
    conn: sqlite3.Connection,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        """,
        (TABLE_NAME,),
    ).fetchone()

    return row is not None


def _verify_contract(
    conn: sqlite3.Connection,
) -> None:
    columns = [
        (
            str(row[1]),
            str(row[2]).upper(),
            int(row[3]),
            int(row[5]),
        )
        for row in conn.execute(
            f"PRAGMA table_info({TABLE_NAME})"
        )
    ]

    expected_columns = [
        ("membership_id", "INTEGER", 1, 1),
        ("permission_id", "INTEGER", 1, 2),
        ("effect", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ]

    if columns != expected_columns:
        raise RuntimeError(
            "override table column contract mismatch: "
            + repr(columns)
        )

    foreign_keys = {
        (
            str(row[3]),
            str(row[2]),
            str(row[4]),
            str(row[5]).upper(),
            str(row[6]).upper(),
        )
        for row in conn.execute(
            f"PRAGMA foreign_key_list({TABLE_NAME})"
        )
    }

    expected_foreign_keys = {
        (
            "membership_id",
            "v155_workspace_members",
            "id",
            "RESTRICT",
            "CASCADE",
        ),
        (
            "permission_id",
            "v155_permissions",
            "id",
            "RESTRICT",
            "CASCADE",
        ),
    }

    if foreign_keys != expected_foreign_keys:
        raise RuntimeError(
            "override table foreign key contract mismatch: "
            + repr(sorted(foreign_keys))
        )

    index_rows = list(
        conn.execute(
            f"PRAGMA index_list({TABLE_NAME})"
        )
    )

    index_names = {
        str(row[1])
        for row in index_rows
    }

    if INDEX_NAME not in index_names:
        raise RuntimeError(
            "required permission index missing"
        )

    index_columns = [
        str(row[2])
        for row in conn.execute(
            f"PRAGMA index_info({INDEX_NAME})"
        )
    ]

    if index_columns != ["permission_id"]:
        raise RuntimeError(
            "permission index column contract mismatch"
        )

    schema_row = conn.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        """,
        (TABLE_NAME,),
    ).fetchone()

    if schema_row is None:
        raise RuntimeError(
            "override table schema missing"
        )

    normalized_sql = " ".join(
        str(schema_row[0] or "")
        .lower()
        .split()
    )

    for required_fragment in (
        "effect",
        "'grant'",
        "'deny'",
        "check",
    ):
        if required_fragment not in normalized_sql:
            raise RuntimeError(
                "override effect constraint mismatch"
            )


def migrate(
    database: str | Path,
    *,
    inject_failure_after_table: bool = False,
) -> dict[str, object]:
    db_path = _resolve_database_path(
        str(database)
    )

    conn = sqlite3.connect(
        str(db_path),
        timeout=15,
    )

    try:
        conn.execute(
            "PRAGMA foreign_keys=ON"
        )

        conn.execute(
            "PRAGMA busy_timeout=15000"
        )

        _required_base_tables_present(
            conn
        )

        existed_before = _table_exists(
            conn
        )

        if existed_before:
            _verify_contract(
                conn
            )

        conn.execute(
            "BEGIN IMMEDIATE"
        )

        try:
            conn.execute(
                CREATE_TABLE_SQL
            )

            if inject_failure_after_table:
                raise RuntimeError(
                    "injected failure after table creation"
                )

            conn.execute(
                CREATE_INDEX_SQL
            )

            _verify_contract(
                conn
            )

            quick_check = str(
                conn.execute(
                    "PRAGMA quick_check"
                ).fetchone()[0]
            )

            if quick_check != "ok":
                raise RuntimeError(
                    "SQLite quick_check failed: "
                    + quick_check
                )

            foreign_key_rows = list(
                conn.execute(
                    "PRAGMA foreign_key_check"
                )
            )

            if foreign_key_rows:
                raise RuntimeError(
                    "foreign key violations detected: "
                    + repr(foreign_key_rows)
                )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        existed_after = _table_exists(
            conn
        )

        override_count = int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM {TABLE_NAME}
                """
            ).fetchone()[0]
        )

        return {
            "database": str(db_path),
            "table_existed_before": existed_before,
            "table_exists_after": existed_after,
            "override_count": override_count,
            "quick_check": quick_check,
            "foreign_key_violation_count": 0,
        }

    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create the V15.5 P0-S17 "
            "workspace-membership permission override schema."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help="Explicit SQLite database path.",
    )

    parser.add_argument(
        "--inject-failure-after-table",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    result = migrate(
        args.database,
        inject_failure_after_table=(
            args.inject_failure_after_table
        ),
    )

    for key in sorted(result):
        print(
            f"{key}={result[key]}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
