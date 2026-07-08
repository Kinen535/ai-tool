#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path("/home/admin/ai-tool")
DB_PATH = ROOT / "data" / "snapshots.db"
APP_PATH = ROOT / "app.py"


REQUIRED_TABLES = [
    "v156_reputation_subjects",
    "v156_reputation_events",
    "v156_reputation_event_relations",
]

REQUIRED_TEMPLATES = [
    "templates/reputation_home.html",
    "templates/reputation_search.html",
    "templates/reputation_subjects.html",
    "templates/reputation_subject_new.html",
    "templates/reputation_subject_edit.html",
    "templates/reputation_subject_detail.html",
    "templates/reputation_events.html",
    "templates/reputation_event_new.html",
    "templates/reputation_event_edit.html",
    "templates/reputation_event_detail.html",
    "templates/reputation_duplicates.html",
    "templates/reputation_merge_logs.html",
]

REQUIRED_ROUTES = [
    '@app.route("/reputation")',
    '@app.route("/reputation/search")',
    '@app.route("/reputation/subjects"',
    '@app.route("/reputation/subjects/new"',
    '@app.route("/reputation/subjects/<int:subject_id>")',
    '@app.route("/reputation/subjects/<int:subject_id>/edit"',
    '@app.route("/reputation/events"',
    '@app.route("/reputation/events/new"',
    '@app.route("/reputation/events/<int:event_id>")',
    '@app.route("/reputation/events/<int:event_id>/edit"',
    '@app.route("/reputation/events/<int:event_id>/relations/save"',
    '@app.route("/reputation/events/<int:event_id>/status"',
    '@app.route("/reputation/duplicates"',
    '@app.route("/reputation/merge-logs"',
]


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def warn(msg: str) -> None:
    print(f"⚠️  {msg}")


def bad(msg: str) -> None:
    print(f"❌ {msg}")


def count_one(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> int:
    row = conn.execute(sql, args).fetchone()
    return int(row[0] or 0) if row else 0


def main() -> int:
    print("V15.6 Reputation Health Check\n# V15.6-A18 reputation health check extended routes/templates")
    print("=" * 48)

    fatal = 0
    warnings = 0

    if not DB_PATH.exists():
        bad(f"数据库不存在：{DB_PATH}")
        return 1

    ok("数据库文件存在")

    if not APP_PATH.exists():
        bad("app.py 不存在")
        return 1

    ok("app.py 存在")

    app_text = APP_PATH.read_text(encoding="utf-8", errors="ignore")

    for route in REQUIRED_ROUTES:
        if route in app_text:
            ok(f"路由存在：{route}")
        else:
            bad(f"路由缺失：{route}")
            fatal += 1

    for tpl in REQUIRED_TEMPLATES:
        p = ROOT / tpl
        if p.exists():
            ok(f"模板存在：{tpl}")
        else:
            bad(f"模板缺失：{tpl}")
            fatal += 1

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    existing_tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    for table in REQUIRED_TABLES:
        if table in existing_tables:
            ok(f"数据表存在：{table}")
        else:
            bad(f"数据表缺失：{table}")
            fatal += 1

    if fatal:
        conn.close()
        print("=" * 48)
        bad(f"体检失败：存在 {fatal} 个基础结构问题")
        return 1

    subject_total = count_one(conn, "SELECT COUNT(*) FROM v156_reputation_subjects")
    event_total = count_one(conn, "SELECT COUNT(*) FROM v156_reputation_events")
    relation_total = count_one(conn, "SELECT COUNT(*) FROM v156_reputation_event_relations")

    risk_subject_total = count_one(
        conn,
        """
        SELECT COUNT(*)
        FROM v156_reputation_subjects
        WHERE risk_level IN ('warning','danger','black')
           OR trust_level IN ('risky','black')
        """,
    )

    high_impact_event_total = count_one(
        conn,
        """
        SELECT COUNT(*)
        FROM v156_reputation_events
        WHERE impact_level IN ('high','severe')
        """,
    )

    print("-" * 48)
    ok(f"信誉主体数量：{subject_total}")
    ok(f"风险主体数量：{risk_subject_total}")
    ok(f"信誉事件数量：{event_total}")
    ok(f"高影响事件数量：{high_impact_event_total}")
    ok(f"事件关联数量：{relation_total}")

    empty_subjects = count_one(
        conn,
        """
        SELECT COUNT(*)
        FROM v156_reputation_subjects
        WHERE IFNULL(TRIM(display_name),'') = ''
          AND IFNULL(TRIM(game_id),'') = ''
        """,
    )

    if empty_subjects:
        warn(f"存在空主体：{empty_subjects} 条")
        warnings += 1
    else:
        ok("没有空主体")

    empty_events = count_one(
        conn,
        """
        SELECT COUNT(*)
        FROM v156_reputation_events
        WHERE IFNULL(TRIM(title),'') = ''
        """,
    )

    if empty_events:
        warn(f"存在空标题事件：{empty_events} 条")
        warnings += 1
    else:
        ok("没有空标题事件")

    orphan_relations = count_one(
        conn,
        """
        SELECT COUNT(*)
        FROM v156_reputation_event_relations r
        LEFT JOIN v156_reputation_subjects s ON s.id = r.subject_id
        LEFT JOIN v156_reputation_events e ON e.id = r.event_id
        WHERE s.id IS NULL OR e.id IS NULL
        """,
    )

    if orphan_relations:
        bad(f"存在断链关联：{orphan_relations} 条")
        fatal += 1
    else:
        ok("没有断链关联")

    duplicate_game_ids = conn.execute(
        """
        SELECT game_id, COUNT(*) AS c
        FROM v156_reputation_subjects
        WHERE IFNULL(TRIM(game_id),'') != ''
        GROUP BY game_id
        HAVING c > 1
        ORDER BY c DESC
        LIMIT 10
        """
    ).fetchall()

    if duplicate_game_ids:
        warn("存在重复游戏编号：")
        for r in duplicate_game_ids:
            print(f"   - {r['game_id']} 重复 {r['c']} 次")
        warnings += 1
    else:
        ok("没有重复游戏编号")

    high_risk_without_event = count_one(
        conn,
        """
        SELECT COUNT(*)
        FROM v156_reputation_subjects s
        LEFT JOIN v156_reputation_event_relations r ON r.subject_id = s.id
        WHERE (
            s.risk_level IN ('warning','danger','black')
            OR s.trust_level IN ('risky','black')
        )
        AND r.id IS NULL
        """,
    )

    if high_risk_without_event:
        warn(f"存在高风险主体但没有关联事件：{high_risk_without_event} 个")
        warnings += 1
    else:
        ok("高风险主体均已有事件关联")

    events_without_subject = count_one(
        conn,
        """
        SELECT COUNT(*)
        FROM v156_reputation_events e
        LEFT JOIN v156_reputation_event_relations r ON r.event_id = e.id
        WHERE r.id IS NULL
        """,
    )

    if events_without_subject:
        warn(f"存在事件但没有关联主体：{events_without_subject} 个")
        warnings += 1
    else:
        ok("所有事件均有关联主体")

    latest_relations = conn.execute(
        """
        SELECT
            r.id,
            e.title,
            s.display_name,
            s.game_id,
            r.relation_role,
            r.created_at
        FROM v156_reputation_event_relations r
        LEFT JOIN v156_reputation_events e ON e.id = r.event_id
        LEFT JOIN v156_reputation_subjects s ON s.id = r.subject_id
        ORDER BY r.id DESC
        LIMIT 5
        """
    ).fetchall()

    if latest_relations:
        print("-" * 48)
        print("最近关联：")
        for r in latest_relations:
            print(
                f"   #{r['id']} {r['display_name'] or '-'} "
                f"({r['game_id'] or '-'}) -> {r['title'] or '-'} "
                f"[{r['relation_role'] or '-'}]"
            )

    conn.close()

    print("=" * 48)

    if fatal:
        bad(f"体检失败：{fatal} 个严重问题，{warnings} 个提醒")
        return 1

    if warnings:
        warn(f"体检完成：基础正常，但有 {warnings} 个数据提醒")
        return 0

    ok("体检完成：信誉档案库基础状态正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
