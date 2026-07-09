#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path("/home/admin/ai-tool")
EXPORT_ROOT = ROOT / "exports" / "reputation"


def run(cmd: list[str], title: str) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)

    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        raise SystemExit(f"❌ 失败：{title}")


def latest_zip() -> Path | None:
    zips = sorted(EXPORT_ROOT.glob("reputation_export_*.zip"))
    return zips[-1] if zips else None


def main() -> int:
    print("V15.6 Reputation Full Chain Check")
    print("=" * 70)

    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "app.py",
            "services/v156_reputation_store.py",
            "scripts/reputation_smoke_test.py",
            "scripts/reputation_health_check.py",
            "scripts/export_reputation_csv.py",
            "scripts/verify_reputation_export.py",
            "scripts/backup_reputation.py",
            "scripts/preview_reputation_restore.py",
        ],
        "Step 1/6：Python 语法编译检查",
    )

    run(
        [sys.executable, "scripts/reputation_smoke_test.py"],
        "Step 2/6：信誉档案库页面烟测",
    )

    run(
        [sys.executable, "scripts/reputation_health_check.py"],
        "Step 3/6：信誉档案库数据体检",
    )

    run(
        [sys.executable, "scripts/backup_reputation.py"],
        "Step 4/6：一键备份导出",
    )

    zip_path = latest_zip()

    if not zip_path:
        raise SystemExit("❌ 没有找到最新 ZIP 备份包")

    run(
        [sys.executable, "scripts/verify_reputation_export.py", str(zip_path)],
        "Step 5/6：ZIP 备份包校验",
    )

    run(
        [sys.executable, "scripts/preview_reputation_restore.py", str(zip_path)],
        "Step 6/6：恢复前预检",
    )

    print("=" * 70)
    print("✅ V15.6 信誉档案库全链路自检通过")
    print(f"✅ 最新备份包：{zip_path}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
