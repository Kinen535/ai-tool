#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path


REQUIRED_FILES = {
    "README.txt",
    "CHECKSUMS.sha256",
    "v156_reputation_subjects.csv",
    "v156_reputation_events.csv",
    "v156_reputation_event_relations.csv",
    "v156_reputation_merge_logs.csv",
}


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def bad(msg: str) -> None:
    print(f"❌ {msg}")


def warn(msg: str) -> None:
    print(f"⚠️  {msg}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split(None, 1)
        if len(parts) != 2:
            continue

        checksum, filename = parts
        result[filename.strip()] = checksum.strip()

    return result


def main() -> int:
    print("V15.6 Reputation Export Verify")
    print("=" * 56)

    if len(sys.argv) != 2:
        bad("用法：python3 scripts/verify_reputation_export.py <export.zip>")
        return 1

    zip_path = Path(sys.argv[1]).resolve()

    if not zip_path.exists():
        bad(f"ZIP 不存在：{zip_path}")
        return 1

    if not zipfile.is_zipfile(zip_path):
        bad(f"不是有效 ZIP 文件：{zip_path}")
        return 1

    ok(f"ZIP 文件存在：{zip_path}")

    fatal = 0
    warnings = 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        with zipfile.ZipFile(zip_path, "r") as z:
            names = set(z.namelist())

            missing = REQUIRED_FILES - names
            extra = names - REQUIRED_FILES

            if missing:
                bad(f"ZIP 缺少必要文件：{sorted(missing)}")
                fatal += 1
            else:
                ok("必要文件齐全")

            if extra:
                warn(f"ZIP 包含额外文件：{sorted(extra)}")
                warnings += 1

            z.extractall(tmp_dir)

        checksum_path = tmp_dir / "CHECKSUMS.sha256"

        if not checksum_path.exists():
            bad("缺少 CHECKSUMS.sha256，无法校验哈希")
            return 1

        checksums = parse_checksums(checksum_path)

        if not checksums:
            bad("CHECKSUMS.sha256 内容为空或格式异常")
            return 1

        ok("CHECKSUMS.sha256 可读取")

        for filename, expected_hash in sorted(checksums.items()):
            file_path = tmp_dir / filename

            if not file_path.exists():
                bad(f"校验清单中的文件不存在：{filename}")
                fatal += 1
                continue

            actual_hash = sha256_file(file_path)

            if actual_hash == expected_hash:
                ok(f"哈希匹配：{filename}")
            else:
                bad(f"哈希不匹配：{filename}")
                print(f"   expected: {expected_hash}")
                print(f"   actual:   {actual_hash}")
                fatal += 1

    print("=" * 56)

    if fatal:
        bad(f"校验失败：{fatal} 个严重问题，{warnings} 个提醒")
        return 1

    if warnings:
        warn(f"校验通过，但有 {warnings} 个提醒")
        return 0

    ok("校验通过：导出包完整、哈希一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
