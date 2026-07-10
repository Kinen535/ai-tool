#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
import re
from pathlib import Path


ROOT = Path("/home/admin/ai-tool")
EXPORT_ROOT = ROOT / "exports" / "reputation"

# V15.6-A32H full check app import path
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# V15.6-A34 full check safe output scrub
def scrub_output(text: str) -> str:
    text = text.replace(str(ROOT), "[PROJECT_ROOT]")
    text = text.replace("/home/admin", "[HOME]")
    text = text.replace("exports/reputation", "[EXPORT_DIR]")
    text = re.sub(r"reputation_export_\d{8}-\d{6}(?:\.zip)?", "reputation_export_[hidden]", text)
    text = re.sub(r"token=[A-Za-z0-9_\-\.]+", "token=[hidden]", text)
    return text


def run(cmd: list[str], title: str) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)

    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(scrub_output(result.stdout), end="" if result.stdout.endswith("\n") else "\n")

    if result.stderr:
        print(scrub_output(result.stderr), end="" if result.stderr.endswith("\n") else "\n")

    if result.returncode != 0:
        raise SystemExit(f"❌ 失败：{title}")




# V15.6-A35 reputation home security check
def check_reputation_home_security() -> None:
    from app import app

    with app.test_client() as c:
        r = c.get("/reputation")
        html = r.data.decode("utf-8", errors="ignore")

        if r.status_code != 200:
            raise SystemExit("❌ 信誉档案库首页访问失败")

        required = [
            "信誉档案",
            "安全备份",
            "维护页已保护",
            "今日处理重点",
            "未关联事件",
            "待核实事件",
            "证据链完整率",
        ]

        forbidden = [
            "/reputation/backup-status",
            "token=",
            "security_admin_token",
            "/home/admin",
            "exports/reputation",
            "python3 scripts/",
            "reputation_export_",
        ]

        for key in required:
            if key not in html:
                raise SystemExit(f"❌ 信誉档案库首页缺少必要内容：{key}")

        for key in forbidden:
            if key in html:
                raise SystemExit(f"❌ 信誉档案库首页暴露敏感内容：{key}")

    print("✅ 信誉档案库首页安全检查通过：维护入口未暴露")


# V15.6-A32G backup status sensitive content check
def check_backup_status_security() -> None:
    from app import app

    token_path = ROOT / "data" / "security_admin_token.txt"
    token = token_path.read_text(encoding="utf-8").strip() if token_path.exists() else ""

    with app.test_client() as c:
        r1 = c.get("/reputation/backup-status")
        if r1.status_code != 404:
            raise SystemExit("❌ 备份状态页无 token 访问未拦截")

        r2 = c.get("/reputation/backup-status", headers={"X-Admin-Token": token})
        html = r2.data.decode("utf-8", errors="ignore")

        if r2.status_code != 200:
            raise SystemExit("❌ 备份状态页 token 访问失败")

        required = [
            "信誉档案库安全备份",
            "最近一次安全备份",
            "维护命令已隐藏",
        ]

        forbidden = [
            "/home/admin",
            "exports/reputation",
            "python3 scripts/",
            "reputation_export_",
            "security_admin_token",
            "backup_reputation.py",
            "reputation_full_check.py",
            "cleanup_reputation_exports.py",
        ]

        for key in required:
            if key not in html:
                raise SystemExit(f"❌ 备份状态页缺少必要内容：{key}")

        for key in forbidden:
            if key in html:
                raise SystemExit(f"❌ 备份状态页暴露敏感内容：{key}")

    print("✅ 备份状态页安全检查通过：无 token 拦截，敏感内容未暴露")


def latest_zip() -> Path | None:
    zips = sorted(EXPORT_ROOT.glob("reputation_export_*.zip"))
    return zips[-1] if zips else None



# V15.6-A38D reputation list chinese visible check
def check_reputation_list_chinese_visible() -> None:
    from app import app
    import re

    pages = [
        "/reputation/subjects",
        "/reputation/events",
        "/reputation/duplicates",
    ]

    forbidden_visible = [
        "black",
        "danger",
        "severe",
        "recorded",
        "pending",
        "disputed",
        "verified",
        "voided",
        "archived",
    ]

    def visible_text(html: str) -> str:
        html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
        html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.I)
        html = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", html)

    with app.test_client() as c:
        combined = ""

        for url in pages:
            r = c.get(url)
            html = r.data.decode("utf-8", errors="ignore")
            text = visible_text(html)
            combined += "\n" + text

            if r.status_code != 200:
                raise SystemExit(f"❌ 列表页访问失败：{url}")

            for key in forbidden_visible:
                if key in text:
                    raise SystemExit(f"❌ 列表页可见文字仍出现英文状态：{url} -> {key}")

        for key in ["黑名单", "严重"]:
            if key not in combined:
                raise SystemExit(f"❌ 列表页缺少中文状态：{key}")

    print("✅ 列表页中文化检查通过：可见文字未发现英文状态")


# V15.6-A39 reputation detail chinese visible check
def check_reputation_detail_chinese_visible() -> None:
    from app import app
    import re

    pages = [
        "/reputation/subjects/8",
        "/reputation/events/3",
        "/reputation/search?q=315789798",
    ]

    forbidden_visible = [
        "black",
        "danger",
        "severe",
        "recorded",
        "pending",
        "disputed",
        "verified",
        "voided",
        "archived",
    ]

    def visible_text(html: str) -> str:
        html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
        html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.I)
        html = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", html)

    with app.test_client() as c:
        combined = ""

        for url in pages:
            r = c.get(url)
            html = r.data.decode("utf-8", errors="ignore")
            text = visible_text(html)
            combined += "\n" + text

            if r.status_code != 200:
                raise SystemExit(f"❌ 详情/检索页访问失败：{url}")

            for key in forbidden_visible:
                if key in text:
                    raise SystemExit(f"❌ 详情/检索页可见文字仍出现英文状态：{url} -> {key}")

        for key in ["证据链", "严重"]:
            if key not in combined:
                raise SystemExit(f"❌ 详情/检索页缺少中文关键内容：{key}")

    print("✅ 详情页与检索页中文化检查通过：可见文字未发现英文状态")


# V15.6-A40 reputation core page security check
def check_reputation_core_pages_security() -> None:
    from app import app

    pages = [
        "/reputation",
        "/reputation/search",
        "/reputation/search?q=315789798",
        "/reputation/subjects",
        "/reputation/subjects/new",
        "/reputation/subjects/8",
        "/reputation/subjects/8/edit",
        "/reputation/events",
        "/reputation/events/new",
        "/reputation/events/3",
        "/reputation/events/3/edit",
        "/reputation/duplicates",
        "/reputation/merge-logs",
    ]

    forbidden = [
        "/home/admin",
        "reputation_export_",
        "token=",
        "security_admin_token",
        "/reputation/backup-status",
        "python3 scripts/",
    ]

    with app.test_client() as c:
        for url in pages:
            r = c.get(url)
            html = r.data.decode("utf-8", errors="ignore")

            if r.status_code != 200:
                raise SystemExit(f"❌ 信誉档案库核心页面异常：{url} -> {r.status_code}")

            for key in forbidden:
                if key in html:
                    raise SystemExit(f"❌ 信誉档案库核心页面暴露敏感内容：{url} -> {key}")

    print("✅ 核心页面巡检通过：页面可访问，未发现敏感内容")

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
        "Step 1/8：Python 语法编译检查",
    )

    run(
        [sys.executable, "scripts/reputation_smoke_test.py"],
        "Step 2/8：信誉档案库页面烟测",
    )

    print("=" * 70)
    print("Step 3/8：信誉档案库首页安全检查")
    print("=" * 70)
    check_reputation_home_security()

    print("=" * 70)
    print("Step 4/8：备份状态页安全检查")
    print("=" * 70)
    check_backup_status_security()

    print("=" * 70)
    print("列表页中文化检查")
    print("=" * 70)
    check_reputation_list_chinese_visible()

    print("=" * 70)
    print("详情页与检索页中文化检查")
    print("=" * 70)
    check_reputation_detail_chinese_visible()

    print("=" * 70)
    print("核心页面巡检")
    print("=" * 70)
    check_reputation_core_pages_security()

    run(
        [sys.executable, "scripts/reputation_health_check.py"],
        "Step 5/8：信誉档案库数据体检",
    )

    run(
        [sys.executable, "scripts/backup_reputation.py"],
        "Step 6/8：一键备份导出",
    )

    zip_path = latest_zip()

    if not zip_path:
        raise SystemExit("❌ 没有找到最新 ZIP 备份包")

    run(
        [sys.executable, "scripts/verify_reputation_export.py", str(zip_path)],
        "Step 7/8：ZIP 备份包校验",
    )

    run(
        [sys.executable, "scripts/preview_reputation_restore.py", str(zip_path)],
        "Step 8/8：恢复前预检",
    )

    print("=" * 70)
    print("✅ V15.6 信誉档案库全链路自检通过")
    print(f"✅ 最新备份包：{scrub_output(str(zip_path))}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
