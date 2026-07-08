#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

# V15.6-A22 fix smoke test import path
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def bad(msg: str) -> None:
    print(f"❌ {msg}")


def warn(msg: str) -> None:
    print(f"⚠️  {msg}")


def main() -> int:
    print("V15.6 Reputation Smoke Test")
    print("=" * 52)

    try:
        from app import app
    except Exception as e:
        bad(f"Flask app 导入失败：{e}")
        return 1

    targets = [
        "/reputation",
        "/reputation/search",
        "/reputation/search?q=315789798",
        "/reputation/search?q=山河ojbk1",
        "/reputation/search?q=无尘ojbk1背刺",
        "/reputation/subjects",
        "/reputation/subjects/new",
        "/reputation/subjects/8",
        "/reputation/events",
        "/reputation/events/new",
        "/reputation/events/3",
        "/reputation/duplicates",
        "/reputation/merge-logs",
    ]

    required_text = {
        "/reputation": ["信誉档案"],
        "/reputation/search?q=315789798": ["证据链", "315789798"],
        "/reputation/subjects": ["主体列表", "关联事件"],
        "/reputation/subjects/8": ["证据链摘要", "关联事件数"],
        "/reputation/events": ["事件列表", "关联主体"],
        "/reputation/events/3": ["关联主体摘要", "关联主体数"],
    }

    fatal = 0
    warnings = 0

    with app.test_client() as c:
        for url in targets:
            r = c.get(url)
            status = r.status_code

            if status == 200:
                ok(f"{url} -> 200")
            elif status == 404:
                bad(f"{url} -> 404 页面不存在")
                fatal += 1
                continue
            elif status >= 500:
                bad(f"{url} -> {status} 服务器错误")
                print(r.data.decode("utf-8", errors="ignore")[:1500])
                fatal += 1
                continue
            else:
                warn(f"{url} -> {status}")
                warnings += 1

            html = r.data.decode("utf-8", errors="ignore")

            if url in required_text:
                for keyword in required_text[url]:
                    if keyword in html:
                        ok(f"{url} 包含关键内容：{keyword}")
                    else:
                        warn(f"{url} 缺少关键内容：{keyword}")
                        warnings += 1

    print("=" * 52)

    if fatal:
        bad(f"烟测失败：{fatal} 个严重问题，{warnings} 个提醒")
        return 1

    if warnings:
        warn(f"烟测完成：基础页面正常，但有 {warnings} 个提醒")
        return 0

    ok("烟测完成：信誉档案库核心页面全部正常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
