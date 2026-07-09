#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import hashlib
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path("/home/admin/ai-tool")
DB_PATH = ROOT / "data" / "snapshots.db"

REQUIRED_FILES = {
    "README.txt",
    "CHECKSUMS.sha256",
    "v156_reputation_subjects.csv",
    "v156_reputation_events.csv",
    "v156_reputation_event_relations.csv",
    "v156_reputation_merge_logs.csv",
}

TABLE_FILES = {
    "v156_reputation_subjects": "v156_reputation_subjects.csv",
    "v156_reputation_events": "v156_reputation_events.csv",
    "v156_reputation_event_relations": "v156_reputation_event_relations.csv",
    "v156_reputation_merge_logs": "v156_reputation_merge_logs.csv",
}


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def warn(msg: str) -> None:
    print(f"⚠️  {msg}")


def bad(msg: str) -> None:
    print(f"❌ {msg}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_checksums(path: Path) -> dict[str, str]:
    result = {}

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split(None, 1)
        if len(parts) == 2:
            result[parts[1].strip()] = parts[0].strip()

    return result


def count_csv_rows(path: Path) -> tuple[int, list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        return 0, []

    header = rows[0]
    data_count = max(len(rows) - 1, 0)
    return data_count, header


def db_count(conn: sqlite3.Connection, table: str) -> int:
    exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()[0]

    if not exists:
        return -1

    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)


def main() -> int:
    print("V15.6 Reputation Restore Preview")
    print("=" * 60)

    if len(sys.argv) != 2:
        bad("用法：python3 scripts/preview_reputation_restore.py <export.zip>")
        return 1

    zip_path = Path(sys.argv[1]).resolve()

    if not zip_path.exists():
        bad(f"ZIP 不存在：{zip_path}")
        return 1

    if not zipfile.is_zipfile(zip_path):
        bad(f"不是有效 ZIP：{zip_path}")
        return 1

    ok(f"ZIP 文件存在：{zip_path}")

    fatal = 0
    warnings = 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        with zipfile.ZipFile(zip_path, "r") as z:
            names = set(z.namelist())

            missing = REQUIRED_FILES - names
            if missing:
                bad(f"ZIP 缺少必要文件：{sorted(missing)}")
                fatal += 1
            else:
                ok("ZIP 必要文件齐全")

            z.extractall(tmp_dir)

        checksum_path = tmp_dir / "CHECKSUMS.sha256"
        checksums = parse_checksums(checksum_path)

        if not checksums:
            bad("CHECKSUMS.sha256 不可读或为空")
            return 1

        ok("CHECKSUMS.sha256 可读取")

        for filename, expected in sorted(checksums.items()):
            p = tmp_dir / filename

            if not p.exists():
                bad(f"校验文件缺失：{filename}")
                fatal += 1
                continue

            actual = sha256_file(p)

            if actual == expected:
                ok(f"哈希匹配：{filename}")
            else:
                bad(f"哈希不匹配：{filename}")
                fatal += 1

        print("-" * 60)
        print("CSV 行数预览：")

        export_counts = {}

        for table, filename in TABLE_FILES.items():
            p = tmp_dir / filename

            if not p.exists():
                bad(f"缺少 CSV：{filename}")
                fatal += 1
                continue

            count, header = count_csv_rows(p)
            export_counts[table] = count
            ok(f"{table}: {count} 行，字段数 {len(header)}")

        print("-" * 60)
        print("当前数据库对比：")

        if not DB_PATH.exists():
            warn(f"当前数据库不存在：{DB_PATH}")
            warnings += 1
        else:
            conn = sqlite3.connect(str(DB_PATH))

            for table, export_count in export_counts.items():
                current_count = db_count(conn, table)

                if current_count < 0:
                    warn(f"{table}: 当前数据库缺少该表，备份包 {export_count} 行")
                    warnings += 1
                else:
                    ok(f"{table}: 当前 {current_count} 行，备份包 {export_count} 行")

            conn.close()

    print("=" * 60)

    if fatal:
        bad(f"恢复预检失败：{fatal} 个严重问题，{warnings} 个提醒")
        return 1

    if warnings:
        warn(f"恢复预检通过，但有 {warnings} 个提醒")
    else:
        ok("恢复预检通过：备份包完整，可进入恢复流程")

    print("提示：本脚本只预检，不会修改数据库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
