#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Optional


TABLES = (
    "v155_archive_alliances",
    "v155_archive_enemies",
    "v155_archive_events",
    "v155_archive_event_relations",
)

INDEXES = (
    (
        "idx_v155_archive_alliances_battle_id",
        "v155_archive_alliances",
    ),
    (
        "idx_v155_archive_enemies_battle_id",
        "v155_archive_enemies",
    ),
    (
        "idx_v155_archive_events_battle_id",
        "v155_archive_events",
    ),
    (
        "idx_v155_archive_event_relations_battle_id",
        "v155_archive_event_relations",
    ),
)


def _table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table,),
    ).fetchone()

    return row is not None


def _columns(
    conn: sqlite3.Connection,
    table: str,
) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    }


def migrate(
    db_path: str,
    *,
    inject_failure_after: Optional[int] = None,
) -> None:
    if not db_path:
        raise ValueError("explicit db_path is required")

    path = Path(db_path).expanduser().resolve()

    conn = sqlite3.connect(
        str(path)
    )

    conn.row_factory = sqlite3.Row

    schema_changes = 0

    try:
        missing = [
            table
            for table in TABLES
            if not _table_exists(
                conn,
                table,
            )
        ]

        if missing:
            raise RuntimeError(
                "required archive table(s) missing: "
                + ", ".join(
                    sorted(
                        missing
                    )
                )
            )

        conn.execute(
            "BEGIN IMMEDIATE"
        )

        for table in TABLES:
            columns = _columns(
                conn,
                table,
            )

            if "battle_id" not in columns:
                conn.execute(
                    f'ALTER TABLE "{table}" '
                    'ADD COLUMN battle_id INTEGER'
                )

                schema_changes += 1

                if (
                    inject_failure_after is not None
                    and schema_changes
                    >= inject_failure_after
                ):
                    raise RuntimeError(
                        "injected migration failure"
                    )

        for index_name, table in INDEXES:
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                f'ON "{table}" (battle_id)'
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Add nullable battle_id ownership columns "
            "to V15.5 P0-S11 archive tables."
        )
    )

    parser.add_argument(
        "--db",
        required=True,
        help="Explicit SQLite database path.",
    )

    parser.add_argument(
        "--inject-failure-after",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    migrate(
        args.db,
        inject_failure_after=args.inject_failure_after,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
