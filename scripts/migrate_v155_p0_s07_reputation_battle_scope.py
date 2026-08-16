#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


TABLES = (
    "v156_reputation_subjects",
    "v156_reputation_events",
    "v156_reputation_event_relations",
)


def columns(conn, table):
    return {
        str(row[1])
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "V15.5 A5 P0-S07 additive reputation "
            "battle provenance migration"
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help="explicit SQLite database path",
    )

    args = parser.parse_args()

    database = Path(args.database).expanduser().resolve()

    if not database.is_file():
        raise SystemExit(
            "database file does not exist: "
            + str(database)
        )

    conn = sqlite3.connect(str(database))

    try:
        conn.execute("BEGIN IMMEDIATE")

        for table in TABLES:
            existing = columns(conn, table)

            if not existing:
                raise RuntimeError(
                    "required table missing: "
                    + table
                )

            if "battle_id" not in existing:
                conn.execute(
                    f"ALTER TABLE {table} "
                    "ADD COLUMN battle_id INTEGER"
                )

        # Historical rows intentionally remain NULL.
        # No current-battle backfill is permitted.

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_v156_rep_subject_battle
            ON v156_reputation_subjects(battle_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_v156_rep_event_battle
            ON v156_reputation_events(battle_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_v156_rep_relation_battle
            ON v156_reputation_event_relations(battle_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_v156_rep_relation_battle_event
            ON v156_reputation_event_relations(
                battle_id,
                event_id
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_v156_rep_relation_battle_subject
            ON v156_reputation_event_relations(
                battle_id,
                subject_id
            )
            """
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    print(
        "V15.5-A5-P0-S07_REPUTATION_BATTLE_SCOPE_MIGRATION=PASS"
    )
    print(
        "legacy_backfill=NONE"
    )
    print(
        "database="
        + str(database)
    )


if __name__ == "__main__":
    main()
