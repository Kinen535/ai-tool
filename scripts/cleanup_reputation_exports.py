#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path("/home/admin/ai-tool")
EXPORT_ROOT = ROOT / "exports" / "reputation"


def collect_exports() -> list[dict]:
    dirs = sorted(EXPORT_ROOT.glob("reputation_export_*"))
    export_dirs = [p for p in dirs if p.is_dir()]

    items = []

    for d in export_dirs:
        zip_path = d.with_suffix(".zip")
        items.append({
            "name": d.name,
            "dir": d,
            "zip": zip_path if zip_path.exists() else None,
        })

    return sorted(items, key=lambda x: x["name"])


def main() -> int:
    parser = argparse.ArgumentParser(description="V15.6 cleanup reputation export backups")
    parser.add_argument("--keep", type=int, default=10, help="保留最近 N 份备份，默认 10")
    parser.add_argument("--apply", action="store_true", help="真正删除；不加则只预览")
    args = parser.parse_args()

    print("V15.6 Reputation Export Cleanup")
    print("=" * 60)

    if not EXPORT_ROOT.exists():
        print(f"⚠️ 导出目录不存在：{EXPORT_ROOT}")
        return 0

    items = collect_exports()

    print(f"当前备份数量：{len(items)}")
    print(f"保留最近数量：{args.keep}")

    if len(items) <= args.keep:
        print("✅ 不需要清理")
        return 0

    to_delete = items[: max(len(items) - args.keep, 0)]

    print("-" * 60)
    print("将清理以下旧备份：")

    for item in to_delete:
        print(f" - {item['dir']}")
        if item["zip"]:
            print(f" - {item['zip']}")

    print("-" * 60)

    if not args.apply:
        print("预览模式：没有删除任何文件。")
        print("确认无误后执行：")
        print(f"python3 scripts/cleanup_reputation_exports.py --keep {args.keep} --apply")
        return 0

    for item in to_delete:
        if item["dir"].exists():
            shutil.rmtree(item["dir"])
            print(f"✅ 已删除目录：{item['dir']}")

        if item["zip"] and item["zip"].exists():
            item["zip"].unlink()
            print(f"✅ 已删除 ZIP：{item['zip']}")

    print("=" * 60)
    print("✅ 清理完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
