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
        "\n        CREATE TABLE IF NOT EXISTS v155_archive_events (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            title TEXT NOT NULL,\n            event_type TEXT DEFAULT '',\n            impact_level TEXT DEFAULT '普通',\n            status TEXT DEFAULT '记录中',\n            related_target TEXT DEFAULT '',\n            description TEXT DEFAULT '',\n            result TEXT DEFAULT '',\n            created_at TEXT DEFAULT '',\n            updated_at TEXT DEFAULT '',\n    battle_id INTEGER\n)\n        "
    )

    conn.execute(
        "\n        CREATE TABLE IF NOT EXISTS v155_archive_alliances (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            name TEXT NOT NULL,\n            relation_status TEXT DEFAULT '观察',\n            trust_level TEXT DEFAULT 'C',\n            contact_name TEXT DEFAULT '',\n            notes TEXT DEFAULT '',\n            created_at TEXT DEFAULT '',\n            updated_at TEXT DEFAULT '',\n    battle_id INTEGER\n)\n        "
    )

    conn.execute(
        "\n        CREATE TABLE IF NOT EXISTS v155_archive_enemies (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            name TEXT NOT NULL,\n            threat_level TEXT DEFAULT '中',\n            activity_level TEXT DEFAULT '未知',\n            tactics TEXT DEFAULT '',\n            core_members TEXT DEFAULT '',\n            notes TEXT DEFAULT '',\n            created_at TEXT DEFAULT '',\n            updated_at TEXT DEFAULT '',\n    battle_id INTEGER\n)\n        "
    )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v155_archive_alliances_battle_id ON v155_archive_alliances (battle_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v155_archive_enemies_battle_id ON v155_archive_enemies (battle_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v155_archive_events_battle_id ON v155_archive_events (battle_id)"
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


def save_event(conn: sqlite3.Connection, data: Dict[str, str], battle_id: int) -> int:
    init_archive_tables(conn)
    now = _now()

    cur = conn.execute(
        '\n        INSERT INTO v155_archive_events\n        (title, event_type, impact_level, status, related_target, description, result, created_at, updated_at, battle_id)\n        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n        ',
        tuple((
            data.get("title", "").strip(),
            data.get("event_type", "").strip(),
            data.get("impact_level", "普通").strip(),
            data.get("status", "记录中").strip(),
            data.get("related_target", "").strip(),
            data.get("description", "").strip(),
            data.get("result", "").strip(),
            now,
            now,
        )) + (battle_id,),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_event(conn: sqlite3.Connection, event_id: int, data: Dict[str, str], battle_id: int) -> None:
    init_archive_tables(conn)
    now = _now()

    conn.execute(
        '\n        UPDATE v155_archive_events\n        SET title=?,\n            event_type=?,\n            impact_level=?,\n            status=?,\n            related_target=?,\n            description=?,\n            result=?,\n            updated_at=?\n        WHERE id=? AND battle_id = ?',
        tuple((
            data.get("title", "").strip(),
            data.get("event_type", "").strip(),
            data.get("impact_level", "普通").strip(),
            data.get("status", "记录中").strip(),
            data.get("related_target", "").strip(),
            data.get("description", "").strip(),
            data.get("result", "").strip(),
            now,
            event_id,
        )) + (battle_id,),
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


# =========================
# V15.5-A2 友盟 / 敌军详情与编辑
# =========================

def get_alliance(conn: sqlite3.Connection, alliance_id: int) -> Optional[Dict[str, Any]]:
    init_archive_tables(conn)
    cur = conn.execute(
        "SELECT * FROM v155_archive_alliances WHERE id=?",
        (alliance_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def update_alliance(conn: sqlite3.Connection, alliance_id: int, data: Dict[str, str], battle_id: int) -> None:
    init_archive_tables(conn)
    now = _now()

    conn.execute(
        '\n        UPDATE v155_archive_alliances\n        SET name=?,\n            relation_status=?,\n            trust_level=?,\n            contact_name=?,\n            notes=?,\n            updated_at=?\n        WHERE id=? AND battle_id = ?',
        tuple((
            data.get("name", "").strip(),
            data.get("relation_status", "观察").strip(),
            data.get("trust_level", "C").strip(),
            data.get("contact_name", "").strip(),
            data.get("notes", "").strip(),
            now,
            alliance_id,
        )) + (battle_id,),
    )
    conn.commit()


def get_enemy(conn: sqlite3.Connection, enemy_id: int) -> Optional[Dict[str, Any]]:
    init_archive_tables(conn)
    cur = conn.execute(
        "SELECT * FROM v155_archive_enemies WHERE id=?",
        (enemy_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def update_enemy(conn: sqlite3.Connection, enemy_id: int, data: Dict[str, str], battle_id: int) -> None:
    init_archive_tables(conn)
    now = _now()

    conn.execute(
        '\n        UPDATE v155_archive_enemies\n        SET name=?,\n            threat_level=?,\n            activity_level=?,\n            tactics=?,\n            core_members=?,\n            notes=?,\n            updated_at=?\n        WHERE id=? AND battle_id = ?',
        tuple((
            data.get("name", "").strip(),
            data.get("threat_level", "中").strip(),
            data.get("activity_level", "未知").strip(),
            data.get("tactics", "").strip(),
            data.get("core_members", "").strip(),
            data.get("notes", "").strip(),
            now,
            enemy_id,
        )) + (battle_id,),
    )
    conn.commit()


# =========================
# V15.5-A3 战场事件关联对象
# =========================

def init_archive_relation_tables(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row

    conn.execute(
        "\n        CREATE TABLE IF NOT EXISTS v155_archive_event_relations (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            event_id INTEGER NOT NULL,\n            target_type TEXT DEFAULT '',\n            target_name TEXT DEFAULT '',\n            note TEXT DEFAULT '',\n            created_at TEXT DEFAULT '',\n    battle_id INTEGER\n)\n        "
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_v155_archive_event_relations_event_id
        ON v155_archive_event_relations(event_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_v155_archive_event_relations_target
        ON v155_archive_event_relations(target_type, target_name)
        """
    )

    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(v155_archive_event_relations)").fetchall()
    }

    if "target_game_id" not in columns:
        conn.execute(
            "ALTER TABLE v155_archive_event_relations ADD COLUMN target_game_id TEXT DEFAULT ''"
        )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_v155_archive_event_relations_game_id
        ON v155_archive_event_relations(target_game_id)
        """
    )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v155_archive_event_relations_battle_id ON v155_archive_event_relations (battle_id)"
    )

    conn.commit()


def archive_target_type_label(target_type: str) -> str:
    mapping = {
        "person": "人物",
        "group": "分组",
        "ally": "友盟",
        "enemy": "敌军",
        "event": "事件",
    }
    return mapping.get(target_type or "", target_type or "-")


def list_event_relations(conn: sqlite3.Connection, event_id: int) -> List[Dict[str, Any]]:
    init_archive_tables(conn)
    init_archive_relation_tables(conn)

    cur = conn.execute(
        """
        SELECT *
        FROM v155_archive_event_relations
        WHERE event_id=?
        ORDER BY id DESC
        """,
        (event_id,),
    )

    rows = _rows(cur)

    for row in rows:
        row["target_type_label"] = archive_target_type_label(row.get("target_type", ""))

    return rows


def save_event_relation(conn: sqlite3.Connection, event_id: int, data: Dict[str, str], battle_id: int) -> int:
    if conn.execute(
        "SELECT 1 FROM v155_archive_events WHERE id = ? AND battle_id = ? LIMIT 1",
        (event_id, battle_id),
    ).fetchone() is None:
        return None

    init_archive_tables(conn)
    init_archive_relation_tables(conn)

    now = _now()

    target_type = data.get("target_type", "").strip()
    target_name = data.get("target_name", "").strip()
    target_game_id = data.get("target_game_id", "").strip()
    note = data.get("note", "").strip()

    if not target_type or not target_name:
        return 0

    cur = conn.execute(
        '\n        INSERT INTO v155_archive_event_relations\n        (event_id, target_type, target_name, target_game_id, note, created_at, battle_id)\n        VALUES (?, ?, ?, ?, ?, ?, ?)\n        ',
        tuple((
            event_id,
            target_type,
            target_name,
            target_game_id,
            note,
            now,
        )) + (battle_id,),
    )

    conn.commit()
    return int(cur.lastrowid)


def delete_event_relation(conn: sqlite3.Connection, event_id: int, relation_id: int, battle_id: int) -> None:
    if conn.execute(
        "SELECT 1 FROM v155_archive_events WHERE id = ? AND battle_id = ? LIMIT 1",
        (event_id, battle_id),
    ).fetchone() is None:
        return None

    init_archive_relation_tables(conn)

    conn.execute(
        '\n        DELETE FROM v155_archive_event_relations\n        WHERE id=? AND event_id=? AND battle_id = ?',
        tuple((relation_id, event_id)) + (battle_id,),
    )

    conn.commit()


def list_related_events_by_target(
    conn: sqlite3.Connection,
    target_type: str,
    target_name: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    init_archive_tables(conn)
    init_archive_relation_tables(conn)

    cur = conn.execute(
        """
        SELECT
            e.*,
            r.note AS relation_note,
            r.created_at AS relation_created_at
        FROM v155_archive_event_relations r
        JOIN v155_archive_events e ON e.id = r.event_id
        WHERE r.target_type=? AND r.target_name=?
        ORDER BY e.id DESC
        LIMIT ?
        """,
        (
            target_type,
            target_name,
            limit,
        ),
    )

    return _rows(cur)
