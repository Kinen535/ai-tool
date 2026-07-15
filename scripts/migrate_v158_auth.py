#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "snapshots.db"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.v158_auth_store import (  # noqa: E402
    ensure_v158_auth_tables,
    get_v158_auth_schema_status,
)


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def connect_writable(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(
        db_path,
        timeout=30,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def create_backup(
    db_path: Path,
    backup_dir: Path,
) -> Path:
    backup_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )

    backup_path = (
        backup_dir
        / f"{db_path.stem}_before_v158_auth_{timestamp}.db"
    )

    source = connect_readonly(db_path)
    target = sqlite3.connect(backup_path)

    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()

    return backup_path


def check_schema(
    db_path: Path,
) -> dict:
    conn = connect_readonly(db_path)

    try:
        status = get_v158_auth_schema_status(conn)
        integrity = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        return {
            **status,
            "integrity_check": integrity,
        }
    finally:
        conn.close()


def apply_schema(
    db_path: Path,
    backup_dir: Path,
) -> tuple[Path, dict]:
    backup_path = create_backup(
        db_path,
        backup_dir,
    )

    conn = connect_writable(db_path)

    try:
        ensure_v158_auth_tables(conn)

        status = get_v158_auth_schema_status(conn)
        integrity = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        status["integrity_check"] = integrity

        if not status.get("ok"):
            raise RuntimeError(
                "认证表或索引创建不完整。"
            )

        if integrity != "ok":
            raise RuntimeError(
                f"数据库完整性检查失败：{integrity}"
            )

        return backup_path, status
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="V15.8认证数据底座迁移工具",
    )

    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help="SQLite数据库路径",
    )

    parser.add_argument(
        "--backup-dir",
        default="/tmp",
        help="执行迁移前的数据库备份目录",
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--check",
        action="store_true",
        help="只读检查认证表结构，不写数据库",
    )

    mode.add_argument(
        "--apply",
        action="store_true",
        help="备份数据库后执行幂等迁移",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    db_path = Path(args.db).expanduser().resolve()

    if not db_path.is_file():
        print(
            f"数据库不存在：{db_path}",
            file=sys.stderr,
        )
        return 1

    if args.apply:
        backup_path, status = apply_schema(
            db_path,
            Path(args.backup_dir).expanduser(),
        )

        print("migration_mode=apply")
        print(f"database={db_path}")
        print(f"backup={backup_path}")
        print(
            json.dumps(
                status,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    status = check_schema(db_path)

    print("migration_mode=check")
    print(f"database={db_path}")
    print(
        json.dumps(
            status,
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    return 0 if status.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
