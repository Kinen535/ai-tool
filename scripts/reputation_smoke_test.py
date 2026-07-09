#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

# V15.6-A29 dynamic smoke test ids
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "snapshots.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def warn(msg: str) -> None:
    print(f"⚠️ {msg}")


def bad(msg: str) -> None:
    print(f"❌ {msg}")


def fetch_sample_data() -> dict:
    data = {
        "subject_id": None,
        "subject_game_id": None,
        "subject_name": None,
        "event_id": None,
        "event_title": None,
    }

    if not DB_PATH.exists():
        warn(f"数据库不存在，动态详情页测试会跳过：{DB_PATH}")
        return data

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        subject = conn.execute(
            """
            SELECT id, display_name, game_id
            FROM v156_reputation_subjects
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if subject:
            data["subject_id"] = subject["id"]
            data["subject_name"] = subject["display_name"]
            data["subject_game_id"] = subject["game_id"]

        event = conn.execute(
            """
            SELECT id, title
            FROM v156_reputation_events
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if event:
            data["event_id"] = event["id"]
            data["event_title"] = event["title"]

    except sqlite3.Error as e:
        warn(f"读取动态测试数据失败：{e}")
    finally:
        conn.close()

    return data


def check_page(client, url: str, required_texts: list[str] | None = None) -> int:
    required_texts = required_texts or []

    r = client.get(url)
    status = r.status_code

    if status == 200:
        ok(f"{url} -> 200")
    else:
        bad(f"{url} -> {status}")
        print(r.data.decode("utf-8", errors="ignore")[:2000])
        return 1

    html = r.data.decode("utf-8", errors="ignore")

    fatal = 0

    for text in required_texts:
        if text in html:
            ok(f"{url} 包含关键内容：{text}")
        else:
            bad(f"{url} 缺少关键内容：{text}")
            fatal += 1

    return fatal


def main() -> int:
    print("V15.6 Reputation Smoke Test")
    print("=" * 52)

    try:
        from app import app
    except Exception as e:
        bad(f"Flask app 导入失败：{e}")
        return 1

    sample = fetch_sample_data()

    targets: list[tuple[str, list[str]]] = [
        ("/reputation", ["信誉档案", "安全备份"]),
        ("/reputation/search", []),
        ("/reputation/subjects", ["主体列表", "关联事件"]),
        ("/reputation/subjects/new", []),
        ("/reputation/events", ["事件列表", "关联主体"]),
        ("/reputation/events/new", []),
        ("/reputation/duplicates", []),
        ("/reputation/merge-logs", []),
        ("/reputation/backup-status", ["信誉档案库安全备份", "最近一次安全备份"]),
    ]

    if sample["subject_game_id"]:
        targets.append(
            (
                f"/reputation/search?q={sample['subject_game_id']}",
                ["证据链", str(sample["subject_game_id"])],
            )
        )

    if sample["subject_name"]:
        targets.append((f"/reputation/search?q={sample['subject_name']}", []))

    if sample["event_title"]:
        targets.append((f"/reputation/search?q={sample['event_title']}", []))

    if sample["subject_id"]:
        targets.append(
            (
                f"/reputation/subjects/{sample['subject_id']}",
                ["证据链摘要", "关联事件数"],
            )
        )
    else:
        warn("没有主体数据，跳过主体详情页测试")

    if sample["event_id"]:
        targets.append(
            (
                f"/reputation/events/{sample['event_id']}",
                ["关联主体摘要", "关联主体数"],
            )
        )
    else:
        warn("没有事件数据，跳过事件详情页测试")

    fatal = 0

    with app.test_client() as client:
        for url, required_texts in targets:
            fatal += check_page(client, url, required_texts)

    print("=" * 52)

    if fatal:
        bad(f"烟测失败：{fatal} 个问题")
        return 1

    ok("烟测完成：信誉档案库核心页面全部正常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
