from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _rows(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    return [dict(row) for row in cur.fetchall()]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def init_archive_tables(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_archive_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            event_type TEXT DEFAULT '',
            impact_level TEXT DEFAULT '普通',
            status TEXT DEFAULT '记录中',
            related_target TEXT DEFAULT '',
            description TEXT DEFAULT '',
            result TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_archive_alliances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            relation_status TEXT DEFAULT '观察',
            trust_level TEXT DEFAULT 'C',
            contact_name TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_archive_enemies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            threat_level TEXT DEFAULT '中',
            activity_level TEXT DEFAULT '未知',
            tactics TEXT DEFAULT '',
            core_members TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
        """
    )

    conn.commit()


def get_archive_overview(conn: sqlite3.Connection) -> Dict[str, Any]:
    init_archive_tables(conn)

    person_count = 0
    group_count = 0

    if _table_exists(conn, "member_profiles"):
        cur = conn.execute(
            "SELECT COUNT(DISTINCT member_name) AS c FROM member_profiles WHERE member_name IS NOT NULL AND member_name != ''"
        )
        row = cur.fetchone()
        person_count = int(row["c"] or 0)

    elif _table_exists(conn, "player_records"):
        cur = conn.execute(
            "SELECT COUNT(DISTINCT member) AS c FROM player_records WHERE member IS NOT NULL AND member != ''"
        )
        row = cur.fetchone()
        person_count = int(row["c"] or 0)

    if _table_exists(conn, "player_records"):
        cur = conn.execute(
            "SELECT COUNT(DISTINCT group_name) AS c FROM player_records WHERE group_name IS NOT NULL AND group_name != ''"
        )
        row = cur.fetchone()
        group_count = int(row["c"] or 0)

    event_count = conn.execute("SELECT COUNT(*) AS c FROM v155_archive_events").fetchone()["c"]
    alliance_count = conn.execute("SELECT COUNT(*) AS c FROM v155_archive_alliances").fetchone()["c"]
    enemy_count = conn.execute("SELECT COUNT(*) AS c FROM v155_archive_enemies").fetchone()["c"]

    return {
        "person_count": person_count,
        "group_count": group_count,
        "event_count": int(event_count or 0),
        "alliance_count": int(alliance_count or 0),
        "enemy_count": int(enemy_count or 0),
        "total_count": person_count + group_count + int(event_count or 0) + int(alliance_count or 0) + int(enemy_count or 0),
        "summary": "V15.5 战场档案库基础闭环已启动：人物档案先复用身份中心，事件、友盟、敌军进入手动沉淀阶段。",
    }


def list_players(conn: sqlite3.Connection, keyword: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    kw = f"%{keyword.strip()}%"

    if _table_exists(conn, "member_profiles"):
        cur = conn.execute(
            """
            SELECT
                member_name AS member,
                current_tag,
                av,
                bs,
                trend,
                risk_level,
                risk_reason,
                role_tag,
                identity_score
            FROM member_profiles
            WHERE member_name LIKE ?
            ORDER BY
                CASE risk_level
                    WHEN 'danger' THEN 1
                    WHEN 'warning' THEN 2
                    WHEN 'protected' THEN 3
                    ELSE 9
                END,
                identity_score DESC,
                av ASC
            LIMIT ?
            """,
            (kw, limit),
        )
        return _rows(cur)

    if _table_exists(conn, "player_records"):
        cur = conn.execute(
            """
            SELECT
                member,
                group_name,
                av,
                bs,
                trend,
                risk_level,
                risk_reason,
                role_tag,
                identity_score
            FROM player_records
            WHERE member LIKE ?
            GROUP BY member
            ORDER BY
                CASE risk_level
                    WHEN 'danger' THEN 1
                    WHEN 'warning' THEN 2
                    WHEN 'protected' THEN 3
                    ELSE 9
                END,
                identity_score DESC,
                av ASC
            LIMIT ?
            """,
            (kw, limit),
        )
        return _rows(cur)

    return []


def list_events(conn: sqlite3.Connection, keyword: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    init_archive_tables(conn)
    kw = f"%{keyword.strip()}%"
    cur = conn.execute(
        """
        SELECT *
        FROM v155_archive_events
        WHERE title LIKE ? OR event_type LIKE ? OR related_target LIKE ? OR description LIKE ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (kw, kw, kw, kw, limit),
    )
    return _rows(cur)


def get_event(conn: sqlite3.Connection, event_id: int) -> Optional[Dict[str, Any]]:
    init_archive_tables(conn)
    cur = conn.execute("SELECT * FROM v155_archive_events WHERE id=?", (event_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def save_event(conn: sqlite3.Connection, data: Dict[str, str]) -> int:
    init_archive_tables(conn)
    now = _now()

    cur = conn.execute(
        """
        INSERT INTO v155_archive_events
        (title, event_type, impact_level, status, related_target, description, result, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("title", "").strip(),
            data.get("event_type", "").strip(),
            data.get("impact_level", "普通").strip(),
            data.get("status", "记录中").strip(),
            data.get("related_target", "").strip(),
            data.get("description", "").strip(),
            data.get("result", "").strip(),
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_event(conn: sqlite3.Connection, event_id: int, data: Dict[str, str]) -> None:
    init_archive_tables(conn)
    now = _now()

    conn.execute(
        """
        UPDATE v155_archive_events
        SET title=?,
            event_type=?,
            impact_level=?,
            status=?,
            related_target=?,
            description=?,
            result=?,
            updated_at=?
        WHERE id=?
        """,
        (
            data.get("title", "").strip(),
            data.get("event_type", "").strip(),
            data.get("impact_level", "普通").strip(),
            data.get("status", "记录中").strip(),
            data.get("related_target", "").strip(),
            data.get("description", "").strip(),
            data.get("result", "").strip(),
            now,
            event_id,
        ),
    )
    conn.commit()


def list_alliances(conn: sqlite3.Connection, keyword: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    init_archive_tables(conn)
    kw = f"%{keyword.strip()}%"
    cur = conn.execute(
        """
        SELECT *
        FROM v155_archive_alliances
        WHERE name LIKE ? OR relation_status LIKE ? OR contact_name LIKE ? OR notes LIKE ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (kw, kw, kw, kw, limit),
    )
    return _rows(cur)


def save_alliance(conn: sqlite3.Connection, data: Dict[str, str]) -> int:
    init_archive_tables(conn)
    now = _now()

    cur = conn.execute(
        """
        INSERT INTO v155_archive_alliances
        (name, relation_status, trust_level, contact_name, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("name", "").strip(),
            data.get("relation_status", "观察").strip(),
            data.get("trust_level", "C").strip(),
            data.get("contact_name", "").strip(),
            data.get("notes", "").strip(),
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_enemies(conn: sqlite3.Connection, keyword: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    init_archive_tables(conn)
    kw = f"%{keyword.strip()}%"
    cur = conn.execute(
        """
        SELECT *
        FROM v155_archive_enemies
        WHERE name LIKE ? OR threat_level LIKE ? OR tactics LIKE ? OR core_members LIKE ? OR notes LIKE ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (kw, kw, kw, kw, kw, limit),
    )
    return _rows(cur)


def save_enemy(conn: sqlite3.Connection, data: Dict[str, str]) -> int:
    init_archive_tables(conn)
    now = _now()

    cur = conn.execute(
        """
        INSERT INTO v155_archive_enemies
        (name, threat_level, activity_level, tactics, core_members, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("name", "").strip(),
            data.get("threat_level", "中").strip(),
            data.get("activity_level", "未知").strip(),
            data.get("tactics", "").strip(),
            data.get("core_members", "").strip(),
            data.get("notes", "").strip(),
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)
