from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Sequence

from services.import_provenance import (
    ensure_snapshot_provenance_schema,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "snapshots.db"


def migrate_import_provenance(
    database_path: Path,
) -> None:
    connection = sqlite3.connect(
        database_path,
        timeout=60,
    )

    try:
        ensure_snapshot_provenance_schema(
            connection
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Add snapshot import provenance "
            "cardinality columns."
        )
    )

    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="SQLite database path; must be supplied explicitly.",
    )

    arguments = parser.parse_args(
        argv
    )

    database_path = (
        arguments.database
        .expanduser()
        .resolve()
    )

    if not database_path.is_file():
        parser.error(
            "database file does not exist: "
            f"{database_path}"
        )

    migrate_import_provenance(
        database_path
    )

    print(
        "Import provenance migration completed: "
        f"{database_path}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
