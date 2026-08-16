#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


TABLE = "v157_reputation_tasks"
COLUMN = "battle_id"
INDEX = "idx_v157_rep_task_battle_id"


def positive_database_path(value: str) -> Path:
    text = str(value or "").strip()

    if not text:
        raise ValueError("--database is required")

    path = Path(text).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(path)

    return path


def table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        '''
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        ''',
        (TABLE,),
    ).fetchone()

    return row is not None


def table_columns(conn: sqlite3.Connection) -> list[str]:
    return [
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{TABLE}")'
        ).fetchall()
    ]


def migrate(database: Path) -> dict[str, object]:
    conn = sqlite3.connect(
        str(database)
    )

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        if not table_exists(conn):
            raise RuntimeError(
                f"required table missing: {TABLE}"
            )

        before = table_columns(conn)

        column_added = False

        if COLUMN not in before:
            conn.execute(
                f'ALTER TABLE "{TABLE}" '
                f'ADD COLUMN "{COLUMN}" INTEGER'
            )
            column_added = True

        conn.execute(
            f'''
            CREATE INDEX IF NOT EXISTS "{INDEX}"
            ON "{TABLE}"(
                "{COLUMN}",
                "id"
            )
            '''
        )

        after = table_columns(conn)

        legacy_null_count = int(
            conn.execute(
                f'''
                SELECT COUNT(*)
                FROM "{TABLE}"
                WHERE "{COLUMN}" IS NULL
                '''
            ).fetchone()[0]
            or 0
        )

        conn.commit()

        return {
            "database": str(database),
            "table": TABLE,
            "column": COLUMN,
            "column_added": column_added,
            "battle_id_present_after": (
                COLUMN in after
            ),
            "legacy_null_count":
                legacy_null_count,
            "historical_backfill_executed":
                False,
            "guessed_provenance_executed":
                False,
            "index": INDEX,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Explicit additive migration for "
            "V15.5-A5-P0-S08 reputation task battle provenance."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help="Explicit SQLite database path.",
    )

    args = parser.parse_args()

    result = migrate(
        positive_database_path(
            args.database
        )
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
