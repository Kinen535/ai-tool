from __future__ import annotations

import argparse
import pathlib
import sqlite3
import sys


TABLE = "v156_reputation_merge_logs"
COLUMN = "battle_id"
INDEX = "idx_v156_reputation_merge_logs_battle_id"


def _table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (TABLE,),
    ).fetchone()

    return row is not None


def _column_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        f"PRAGMA table_info({TABLE})"
    ).fetchall()

    return {
        str(row[1])
        for row in rows
    }


def migrate(db_path: str | pathlib.Path) -> dict[str, object]:
    path = pathlib.Path(db_path)

    if not path.exists():
        raise FileNotFoundError(
            f"database does not exist: {path}"
        )

    conn = sqlite3.connect(
        str(path)
    )

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        if not _table_exists(conn):
            raise RuntimeError(
                f"required table is missing: {TABLE}"
            )

        columns_before = _column_names(
            conn
        )

        column_added = False

        if COLUMN not in columns_before:
            conn.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN {COLUMN} INTEGER
                """
            )
            column_added = True

        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {INDEX}
            ON {TABLE}({COLUMN})
            """
        )

        columns_after = _column_names(
            conn
        )

        if COLUMN not in columns_after:
            raise RuntimeError(
                f"migration invariant failed: {COLUMN} missing"
            )

        conn.commit()

        return {
            "table": TABLE,
            "column": COLUMN,
            "index": INDEX,
            "column_added": column_added,
            "historical_backfill": False,
            "guessed_provenance": False,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Add nullable battle_id and supporting index "
            "to v156_reputation_merge_logs without backfill."
        )
    )

    parser.add_argument(
        "db_path",
        help=(
            "Explicit SQLite database path. "
            "No production path is assumed or defaulted."
        ),
    )

    args = parser.parse_args()

    result = migrate(
        args.db_path
    )

    for key in sorted(result):
        print(
            f"{key}={result[key]}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
