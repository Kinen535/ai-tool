#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path("/home/admin/ai-tool")
EXPORT_ROOT = ROOT / "exports" / "reputation"


def run(cmd: list[str], title: str) -> None:
    print("=" * 60)
    print(title)
    print("=" * 60)
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        raise SystemExit(f"❌ 失败：{title}")


def latest_zip() -> Path | None:
    zips = sorted(EXPORT_ROOT.glob("reputation_export_*.zip"))
    return zips[-1] if zips else None


def main() -> int:
    print("V15.7 Reputation One-Click Backup")
    print("=" * 60)

    run(
        [sys.executable, "scripts/reputation_health_check.py"],
        "Step 1/3：信誉档案库体检",
    )

    run(
        [sys.executable, "scripts/export_reputation_csv.py"],
        "Step 2/3：导出 CSV + ZIP",
    )

    zip_path = latest_zip()

    if not zip_path:
        raise SystemExit("❌ 没有找到导出的 ZIP 包")

    run(
        [sys.executable, "scripts/verify_reputation_export.py", str(zip_path)],
        "Step 3/3：校验 ZIP 完整性",
    )

    print("=" * 60)
    print("✅ 信誉档案库备份完成")
    print(f"备份包：{zip_path}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
