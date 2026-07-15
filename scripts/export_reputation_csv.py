#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import sqlite3
import zipfile
import hashlib
from datetime import datetime
from pathlib import Path


ROOT = Path("/home/admin/ai-tool")
DB_PATH = ROOT / "data" / "snapshots.db"
EXPORT_ROOT = ROOT / "exports" / "reputation"


TABLES = [
    "v156_reputation_subjects",
    "v156_reputation_events",
    "v156_reputation_event_relations",
    "v156_reputation_merge_logs",
    # V15.7-A7-4 reputation task export
    "v157_reputation_tasks",
]


def export_table(conn: sqlite3.Connection, table: str, out_dir: Path) -> int:
    exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()[0]

    if not exists:
        print(f"⚠️ 跳过不存在的数据表：{table}")
        return 0

    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    columns = [d[0] for d in conn.execute(f"SELECT * FROM {table} LIMIT 1").description]

    out_file = out_dir / f"{table}.csv"

    with out_file.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row[col] for col in columns])

    print(f"✅ 已导出：{table} -> {out_file}，{len(rows)} 行")
    return len(rows)



# V15.6-A25 reputation export zip package
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksums(out_dir: Path) -> Path:
    checksum_file = out_dir / "CHECKSUMS.sha256"
    lines = []

    for p in sorted(out_dir.glob("*")):
        if p.is_file() and p.name != "CHECKSUMS.sha256":
            lines.append(f"{sha256_file(p)}  {p.name}")

    checksum_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checksum_file


def make_zip(out_dir: Path) -> Path:
    zip_path = out_dir.with_suffix(".zip")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out_dir.glob("*")):
            if p.is_file():
                z.write(p, arcname=p.name)

    return zip_path


def main() -> int:
    print("V15.7 Reputation CSV Export")
    print("=" * 56)

    if not DB_PATH.exists():
        print(f"❌ 数据库不存在：{DB_PATH}")
        return 1

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = EXPORT_ROOT / f"reputation_export_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    total = 0
    for table in TABLES:
        total += export_table(conn, table, out_dir)

    summary_file = out_dir / "README.txt"
    summary_file.write_text(
        "\n".join([
            "V15.7 Reputation CSV Export",
            f"Export time: {ts}",
            f"Database: {DB_PATH}",
            f"Total exported rows: {total}",
            "",
            "Files:",
            *[f"- {table}.csv" for table in TABLES],
            "",
        ]),
        encoding="utf-8",
    )

    checksum_file = write_checksums(out_dir)
    zip_path = make_zip(out_dir)

    conn.close()

    print("-" * 56)
    print(f"✅ 校验清单：{checksum_file}")
    print(f"✅ ZIP 包：{zip_path}")
    print(f"✅ 导出完成：{out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
