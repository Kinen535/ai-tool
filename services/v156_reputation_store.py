from __future__ import annotations
import re

import sqlite3
from typing import Any


def _a4_legacy_ensure_reputation_tables(conn: sqlite3.Connection) -> None:
    """
    V15.6 信誉档案库基础表。
    注意：这是独立于当前战场 battle_id 的私有信誉档案库。
    """
    conn.execute("\n        CREATE TABLE IF NOT EXISTS v156_reputation_subjects (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            battle_id INTEGER,\n            subject_type TEXT DEFAULT 'player',\n            display_name TEXT,\n            game_id TEXT,\n            alias_names TEXT DEFAULT '',\n            trust_level TEXT DEFAULT 'unknown',\n            risk_level TEXT DEFAULT 'normal',\n            status TEXT DEFAULT 'active',\n            source_type TEXT DEFAULT 'manual',\n            note TEXT DEFAULT '',\n            created_at TEXT DEFAULT (datetime('now','localtime')),\n            updated_at TEXT DEFAULT (datetime('now','localtime'))\n        )\n        ")
    conn.execute("\n        CREATE TABLE IF NOT EXISTS v156_reputation_events (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            battle_id INTEGER,\n            title TEXT,\n            event_type TEXT DEFAULT 'general',\n            impact_level TEXT DEFAULT 'normal',\n            status TEXT DEFAULT 'recorded',\n            event_time TEXT DEFAULT '',\n            summary TEXT DEFAULT '',\n            evidence_note TEXT DEFAULT '',\n            created_at TEXT DEFAULT (datetime('now','localtime')),\n            updated_at TEXT DEFAULT (datetime('now','localtime'))\n        )\n        ")
    conn.execute("\n        CREATE TABLE IF NOT EXISTS v156_reputation_event_relations (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            battle_id INTEGER,\n            event_id INTEGER,\n            subject_id INTEGER,\n            relation_role TEXT DEFAULT '',\n            note TEXT DEFAULT '',\n            created_at TEXT DEFAULT (datetime('now','localtime'))\n        )\n        ")
    conn.execute('\n        CREATE INDEX IF NOT EXISTS idx_v156_rep_subject_game_id\n        ON v156_reputation_subjects(game_id)\n        ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS idx_v156_rep_subject_name\n        ON v156_reputation_subjects(display_name)\n        ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS idx_v156_rep_event_rel_subject\n        ON v156_reputation_event_relations(subject_id)\n        ')
    conn.execute("\n        CREATE TABLE IF NOT EXISTS v157_reputation_tasks (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            battle_id INTEGER,\n            entity_type TEXT NOT NULL DEFAULT 'subject',\n            entity_id INTEGER NOT NULL,\n            entity_name TEXT DEFAULT '',\n            entity_identifier TEXT DEFAULT '',\n            priority TEXT NOT NULL DEFAULT 'P3',\n            task_reason TEXT DEFAULT '',\n            recommended_action TEXT DEFAULT '',\n            owner TEXT DEFAULT '',\n            status TEXT NOT NULL DEFAULT 'pending',\n            result_note TEXT DEFAULT '',\n            source_type TEXT DEFAULT 'workbench',\n            created_at TEXT DEFAULT (\n                datetime('now','localtime')\n            ),\n            updated_at TEXT DEFAULT (\n                datetime('now','localtime')\n            ),\n            completed_at TEXT DEFAULT ''\n        )\n        ")
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_v157_rep_task_status\n        ON v157_reputation_tasks(status)\n        ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_v157_rep_task_priority\n        ON v157_reputation_tasks(priority)\n        ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_v157_rep_task_entity\n        ON v157_reputation_tasks(\n            entity_type,\n            entity_id\n        )\n        ')
    conn.execute("\n        CREATE UNIQUE INDEX IF NOT EXISTS\n        idx_v157_rep_task_active_unique\n        ON v157_reputation_tasks(\n            entity_type,\n            entity_id\n        )\n        WHERE status IN (\n            'pending',\n            'processing'\n        )\n        ")
    conn.commit()
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_v156_rep_subject_battle\n        ON v156_reputation_subjects(battle_id)\n        ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_v156_rep_event_battle\n        ON v156_reputation_events(battle_id)\n        ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_v156_rep_relation_battle\n        ON v156_reputation_event_relations(battle_id)\n        ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_v156_rep_relation_battle_event\n        ON v156_reputation_event_relations(\n            battle_id,\n            event_id\n        )\n        ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_v156_rep_relation_battle_subject\n        ON v156_reputation_event_relations(\n            battle_id,\n            subject_id\n        )\n        ')
    conn.execute('\n    CREATE INDEX IF NOT EXISTS\n    idx_v157_rep_task_battle_id\n    ON v157_reputation_tasks(\n        battle_id,\n        id\n    )\n    ')


def get_reputation_dashboard(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_reputation_tables(conn)

    def count(sql: str, params: tuple = ()) -> int:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] or 0) if row else 0

    total_subjects = count("SELECT COUNT(*) FROM v156_reputation_subjects")
    risky_subjects = count(
        """
        SELECT COUNT(*)
        FROM v156_reputation_subjects
        WHERE risk_level IN ('warning','danger','black')
        """
    )
    total_events = count("SELECT COUNT(*) FROM v156_reputation_events")
    linked_events = count(
        """
        SELECT COUNT(DISTINCT event_id)
        FROM v156_reputation_event_relations
        """
    )

    recent_subjects = conn.execute(
        """
        SELECT *
        FROM v156_reputation_subjects
        ORDER BY id DESC
        LIMIT 8
        """
    ).fetchall()

    recent_events = conn.execute(
        """
        SELECT *
        FROM v156_reputation_events
        ORDER BY id DESC
        LIMIT 8
        """
    ).fetchall()

    return {
        "total_subjects": total_subjects,
        "risky_subjects": risky_subjects,
        "total_events": total_events,
        "linked_events": linked_events,
        "recent_subjects": recent_subjects,
        "recent_events": recent_events,
    }


def search_reputation(conn: sqlite3.Connection, q: str) -> dict[str, Any]:
    # V15.6-A5.1 search relation display
    ensure_reputation_tables(conn)

    q = (q or "").strip()

    if not q:
        return {
            "query": q,
            "subjects": [],
            "events": [],
            "event_relation_map": {},
        }

    like = f"%{q}%"

    subjects = conn.execute(
        """
        SELECT *
        FROM v156_reputation_subjects
        WHERE display_name LIKE ?
           OR game_id LIKE ?
           OR alias_names LIKE ?
           OR note LIKE ?
        ORDER BY id DESC
        LIMIT 30
        """,
        (like, like, like, like),
    ).fetchall()

    events = conn.execute(
        """
        SELECT DISTINCT e.*
        FROM v156_reputation_events e
        LEFT JOIN v156_reputation_event_relations r ON r.event_id = e.id
        LEFT JOIN v156_reputation_subjects s ON s.id = r.subject_id
        WHERE e.title LIKE ?
           OR e.summary LIKE ?
           OR e.evidence_note LIKE ?
           OR s.display_name LIKE ?
           OR s.game_id LIKE ?
           OR s.alias_names LIKE ?
        ORDER BY e.id DESC
        LIMIT 30
        """,
        (like, like, like, like, like, like),
    ).fetchall()

    event_relation_map: dict[int, list] = {}

    event_ids = [int(e["id"]) for e in events]

    if event_ids:
        placeholders = ",".join(["?"] * len(event_ids))

        relation_rows = conn.execute(
            f"""
            SELECT
                r.*,
                s.display_name,
                s.game_id,
                s.alias_names,
                s.trust_level,
                s.risk_level,
                s.status AS subject_status
            FROM v156_reputation_event_relations r
            LEFT JOIN v156_reputation_subjects s ON s.id = r.subject_id
            WHERE r.event_id IN ({placeholders})
            ORDER BY r.id DESC
            """,
            tuple(event_ids),
        ).fetchall()

        for row in relation_rows:
            event_id = int(row["event_id"])
            event_relation_map.setdefault(event_id, []).append(row)

    return {
        "query": q,
        "subjects": subjects,
        "events": events,
        "event_relation_map": event_relation_map,
    }


# =========================
# V15.6-A3 reputation subject CRUD
# =========================

def list_reputation_subjects(
    conn: sqlite3.Connection,
    q: str = "",
    limit: int = 100,
) -> list:
    ensure_reputation_tables(conn)

    q = (q or "").strip()

    if not q:
        return conn.execute(
            """
            SELECT *
            FROM v156_reputation_subjects
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    like = f"%{q}%"

    return conn.execute(
        """
        SELECT *
        FROM v156_reputation_subjects
        WHERE display_name LIKE ?
           OR game_id LIKE ?
           OR alias_names LIKE ?
           OR note LIKE ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (like, like, like, like, limit),
    ).fetchall()


def get_reputation_subject(
    conn: sqlite3.Connection,
    subject_id: int,
):
    ensure_reputation_tables(conn)

    return conn.execute(
        """
        SELECT *
        FROM v156_reputation_subjects
        WHERE id=?
        """,
        (subject_id,),
    ).fetchone()


def create_reputation_subject(
    conn: sqlite3.Connection,
    data: dict[str, Any],
) -> int | None:
    ensure_reputation_tables(conn)

    display_name = (data.get("display_name") or "").strip()
    game_id = (data.get("game_id") or "").strip()

    if not display_name and not game_id:
        return None

    cur = conn.execute(
        """
        INSERT INTO v156_reputation_subjects (
            subject_type,
            display_name,
            game_id,
            alias_names,
            trust_level,
            risk_level,
            status,
            source_type,
            note,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
        """,
        (
            (data.get("subject_type") or "player").strip(),
            display_name,
            game_id,
            (data.get("alias_names") or "").strip(),
            (data.get("trust_level") or "unknown").strip(),
            (data.get("risk_level") or "normal").strip(),
            (data.get("status") or "active").strip(),
            (data.get("source_type") or "manual").strip(),
            (data.get("note") or "").strip(),
        ),
    )

    conn.commit()
    return int(cur.lastrowid)


def update_reputation_subject(
    conn: sqlite3.Connection,
    subject_id: int,
    data: dict[str, Any],
) -> bool:
    ensure_reputation_tables(conn)

    display_name = (data.get("display_name") or "").strip()
    game_id = (data.get("game_id") or "").strip()

    if not display_name and not game_id:
        return False

    conn.execute(
        """
        UPDATE v156_reputation_subjects
        SET
            subject_type=?,
            display_name=?,
            game_id=?,
            alias_names=?,
            trust_level=?,
            risk_level=?,
            status=?,
            source_type=?,
            note=?,
            updated_at=datetime('now','localtime')
        WHERE id=?
        """,
        (
            (data.get("subject_type") or "player").strip(),
            display_name,
            game_id,
            (data.get("alias_names") or "").strip(),
            (data.get("trust_level") or "unknown").strip(),
            (data.get("risk_level") or "normal").strip(),
            (data.get("status") or "active").strip(),
            (data.get("source_type") or "manual").strip(),
            (data.get("note") or "").strip(),
            subject_id,
        ),
    )

    conn.commit()
    return True


def delete_reputation_subject(
    conn: sqlite3.Connection,
    subject_id: int,
) -> None:
    ensure_reputation_tables(conn)

    conn.execute(
        """
        DELETE FROM v156_reputation_event_relations
        WHERE subject_id=?
        """,
        (subject_id,),
    )

    conn.execute(
        """
        DELETE FROM v156_reputation_subjects
        WHERE id=?
        """,
        (subject_id,),
    )

    conn.commit()


# =========================
# V15.6-A4 reputation event CRUD
# =========================

def list_reputation_events(
    conn: sqlite3.Connection,
    q: str = "",
    limit: int = 100,
) -> list:
    ensure_reputation_tables(conn)

    q = (q or "").strip()

    if not q:
        return conn.execute(
            """
            SELECT *
            FROM v156_reputation_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    like = f"%{q}%"

    return conn.execute(
        """
        SELECT *
        FROM v156_reputation_events
        WHERE title LIKE ?
           OR event_type LIKE ?
           OR impact_level LIKE ?
           OR status LIKE ?
           OR summary LIKE ?
           OR evidence_note LIKE ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (like, like, like, like, like, like, limit),
    ).fetchall()


def get_reputation_event(
    conn: sqlite3.Connection,
    event_id: int,
):
    ensure_reputation_tables(conn)

    return conn.execute(
        """
        SELECT *
        FROM v156_reputation_events
        WHERE id=?
        """,
        (event_id,),
    ).fetchone()


def create_reputation_event(
    conn: sqlite3.Connection,
    data: dict[str, Any],
) -> int | None:
    ensure_reputation_tables(conn)

    title = (data.get("title") or "").strip()

    if not title:
        return None

    cur = conn.execute(
        """
        INSERT INTO v156_reputation_events (
            title,
            event_type,
            impact_level,
            status,
            event_time,
            summary,
            evidence_note,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
        """,
        (
            title,
            (data.get("event_type") or "general").strip(),
            (data.get("impact_level") or "normal").strip(),
            (data.get("status") or "recorded").strip(),
            (data.get("event_time") or "").strip(),
            (data.get("summary") or "").strip(),
            (data.get("evidence_note") or "").strip(),
        ),
    )

    conn.commit()
    return int(cur.lastrowid)


def update_reputation_event(
    conn: sqlite3.Connection,
    event_id: int,
    data: dict[str, Any],
) -> bool:
    ensure_reputation_tables(conn)

    title = (data.get("title") or "").strip()

    if not title:
        return False

    conn.execute(
        """
        UPDATE v156_reputation_events
        SET
            title=?,
            event_type=?,
            impact_level=?,
            status=?,
            event_time=?,
            summary=?,
            evidence_note=?,
            updated_at=datetime('now','localtime')
        WHERE id=?
        """,
        (
            title,
            (data.get("event_type") or "general").strip(),
            (data.get("impact_level") or "normal").strip(),
            (data.get("status") or "recorded").strip(),
            (data.get("event_time") or "").strip(),
            (data.get("summary") or "").strip(),
            (data.get("evidence_note") or "").strip(),
            event_id,
        ),
    )

    conn.commit()
    return True


def delete_reputation_event(
    conn: sqlite3.Connection,
    event_id: int,
) -> None:
    ensure_reputation_tables(conn)

    conn.execute(
        """
        DELETE FROM v156_reputation_event_relations
        WHERE event_id=?
        """,
        (event_id,),
    )

    conn.execute(
        """
        DELETE FROM v156_reputation_events
        WHERE id=?
        """,
        (event_id,),
    )

    conn.commit()


# =========================
# V15.6-A5 reputation event relations
# =========================

def list_reputation_event_relations(
    conn: sqlite3.Connection,
    event_id: int,
) -> list:
    ensure_reputation_tables(conn)

    return conn.execute(
        """
        SELECT
            r.*,
            s.display_name,
            s.game_id,
            s.alias_names,
            s.trust_level,
            s.risk_level,
            s.status AS subject_status
        FROM v156_reputation_event_relations r
        LEFT JOIN v156_reputation_subjects s ON s.id = r.subject_id
        WHERE r.event_id=?
        ORDER BY r.id DESC
        """,
        (event_id,),
    ).fetchall()


def add_reputation_event_relation(
    conn: sqlite3.Connection,
    event_id: int,
    subject_id: int,
    relation_role: str = "",
    note: str = "",
) -> bool:
    ensure_reputation_tables(conn)

    if not event_id or not subject_id:
        return False

    event = conn.execute(
        "SELECT id FROM v156_reputation_events WHERE id=?",
        (event_id,),
    ).fetchone()

    subject = conn.execute(
        "SELECT id FROM v156_reputation_subjects WHERE id=?",
        (subject_id,),
    ).fetchone()

    if not event or not subject:
        return False

    exists = conn.execute(
        """
        SELECT id
        FROM v156_reputation_event_relations
        WHERE event_id=? AND subject_id=?
        """,
        (event_id, subject_id),
    ).fetchone()

    if exists:
        conn.execute(
            """
            UPDATE v156_reputation_event_relations
            SET relation_role=?, note=?
            WHERE id=?
            """,
            (
                (relation_role or "").strip(),
                (note or "").strip(),
                exists["id"],
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO v156_reputation_event_relations (
                event_id,
                subject_id,
                relation_role,
                note
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                event_id,
                subject_id,
                (relation_role or "").strip(),
                (note or "").strip(),
            ),
        )

    conn.commit()
    return True


def delete_reputation_event_relation(
    conn: sqlite3.Connection,
    relation_id: int,
) -> None:
    ensure_reputation_tables(conn)

    conn.execute(
        """
        DELETE FROM v156_reputation_event_relations
        WHERE id=?
        """,
        (relation_id,),
    )

    conn.commit()


# =========================
# V15.6-A6 reputation subject detail
# =========================

def list_reputation_events_by_subject(
    conn: sqlite3.Connection,
    subject_id: int,
) -> list:
    ensure_reputation_tables(conn)

    return conn.execute(
        """
        SELECT
            e.*,
            r.id AS relation_id,
            r.relation_role,
            r.note AS relation_note,
            r.created_at AS relation_created_at
        FROM v156_reputation_event_relations r
        LEFT JOIN v156_reputation_events e ON e.id = r.event_id
        WHERE r.subject_id=?
        ORDER BY e.id DESC
        """,
        (subject_id,),
    ).fetchall()


# =========================
# V15.6-A8 reputation home dashboard
# =========================

def build_reputation_home_report(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_reputation_tables(conn)

    def one(sql: str, args: tuple = ()) -> int:
        row = conn.execute(sql, args).fetchone()
        return int(row[0] or 0) if row else 0

    subject_total = one("SELECT COUNT(*) FROM v156_reputation_subjects")

    risk_subject_total = one(
        """
        SELECT COUNT(*)
        FROM v156_reputation_subjects
        WHERE risk_level IN ('warning', 'danger', 'black')
           OR trust_level IN ('risky', 'black')
        """
    )

    black_subject_total = one(
        """
        SELECT COUNT(*)
        FROM v156_reputation_subjects
        WHERE risk_level='black'
           OR trust_level='black'
        """
    )

    event_total = one("SELECT COUNT(*) FROM v156_reputation_events")

    severe_event_total = one(
        """
        SELECT COUNT(*)
        FROM v156_reputation_events
        WHERE impact_level IN ('high', 'severe')
        """
    )

    relation_total = one("SELECT COUNT(*) FROM v156_reputation_event_relations")

    # V15.6-A36 reputation home business dashboard
    unlinked_event_total = one(
        """
        SELECT COUNT(*)
        FROM v156_reputation_events e
        LEFT JOIN v156_reputation_event_relations r ON r.event_id = e.id
        WHERE r.id IS NULL
          AND IFNULL(e.status, '') NOT IN ('voided', 'archived')
        """
    )

    pending_event_total = one(
        """
        SELECT COUNT(*)
        FROM v156_reputation_events
        WHERE IFNULL(status, '') IN ('pending', 'disputed')
        """
    )

    linked_subject_total = one(
        """
        SELECT COUNT(DISTINCT subject_id)
        FROM v156_reputation_event_relations
        """
    )

    evidence_complete_rate = 0
    if subject_total > 0:
        evidence_complete_rate = round(linked_subject_total * 100 / subject_total, 1)

    high_risk_subjects = conn.execute(
        """
        SELECT *
        FROM v156_reputation_subjects
        WHERE risk_level IN ('warning', 'danger', 'black')
           OR trust_level IN ('risky', 'black')
        ORDER BY
            CASE
                WHEN risk_level='black' THEN 1
                WHEN risk_level='danger' THEN 2
                WHEN trust_level='black' THEN 3
                WHEN trust_level='risky' THEN 4
                WHEN risk_level='warning' THEN 5
                ELSE 9
            END,
            updated_at DESC,
            id DESC
        LIMIT 8
        """
    ).fetchall()

    recent_events = conn.execute(
        """
        SELECT *
        FROM v156_reputation_events
        ORDER BY updated_at DESC, id DESC
        LIMIT 8
        """
    ).fetchall()

    unlinked_events = conn.execute(
        """
        SELECT e.*
        FROM v156_reputation_events e
        LEFT JOIN v156_reputation_event_relations r ON r.event_id = e.id
        WHERE r.id IS NULL
          AND IFNULL(e.status, '') NOT IN ('voided', 'archived')
        ORDER BY e.updated_at DESC, e.id DESC
        LIMIT 6
        """
    ).fetchall()

    pending_events = conn.execute(
        """
        SELECT *
        FROM v156_reputation_events
        WHERE IFNULL(status, '') IN ('pending', 'disputed')
        ORDER BY updated_at DESC, id DESC
        LIMIT 6
        """
    ).fetchall()

    recent_relations = conn.execute(
        """
        SELECT
            r.*,
            e.title,
            e.impact_level,
            e.status AS event_status,
            s.display_name,
            s.game_id,
            s.risk_level,
            s.trust_level
        FROM v156_reputation_event_relations r
        LEFT JOIN v156_reputation_events e ON e.id = r.event_id
        LEFT JOIN v156_reputation_subjects s ON s.id = r.subject_id
        ORDER BY r.id DESC
        LIMIT 8
        """
    ).fetchall()

    if black_subject_total > 0:
        stage_tip = "已有黑名单或高危主体，建议优先补充事件证据和关联关系。"
    elif risk_subject_total > 0:
        stage_tip = "已有风险主体，建议继续完善事件库与主体详情。"
    elif subject_total > 0 or event_total > 0:
        stage_tip = "基础数据已开始沉淀，下一步建议补充关联关系。"
    else:
        stage_tip = "当前仍是空库，建议先录入主体和事件。"

    return {
        "stats": {
            "subject_total": subject_total,
            "risk_subject_total": risk_subject_total,
            "black_subject_total": black_subject_total,
            "event_total": event_total,
            "severe_event_total": severe_event_total,
            "relation_total": relation_total,
            "unlinked_event_total": unlinked_event_total,
            "pending_event_total": pending_event_total,
            "linked_subject_total": linked_subject_total,
            "evidence_complete_rate": evidence_complete_rate,
        },
        "high_risk_subjects": high_risk_subjects,
        "recent_events": recent_events,
        "unlinked_events": unlinked_events,
        "pending_events": pending_events,
        "recent_relations": recent_relations,
        "stage_tip": stage_tip,
    }


# =========================
# V15.6-A11 reputation duplicate detection and merge
# =========================

def _v156_subject_ids_to_rows(conn: sqlite3.Connection, ids: list[int]) -> list:
    if not ids:
        return []

    placeholders = ",".join(["?"] * len(ids))

    rows = conn.execute(
        f"""
        SELECT
            s.*,
            COUNT(r.id) AS relation_count
        FROM v156_reputation_subjects s
        LEFT JOIN v156_reputation_event_relations r ON r.subject_id = s.id
        WHERE s.id IN ({placeholders})
        GROUP BY s.id
        """,
        tuple(ids),
    ).fetchall()

    def score(row):
        relation_count = int(row["relation_count"] or 0)

        risk_rank = {
            "normal": 0,
            "warning": 1,
            "danger": 2,
            "black": 3,
        }.get((row["risk_level"] or "").strip(), 0)

        trust_rank = {
            "unknown": 0,
            "trusted": 1,
            "risky": 2,
            "black": 3,
        }.get((row["trust_level"] or "").strip(), 0)

        updated_at = row["updated_at"] or ""
        row_id = int(row["id"] or 0)

        return (
            relation_count,
            risk_rank,
            trust_rank,
            updated_at,
            row_id,
        )

    return sorted(rows, key=score, reverse=True)


def build_reputation_duplicate_report(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_reputation_tables(conn)

    groups: list[dict[str, Any]] = []

    game_id_groups = conn.execute(
        """
        SELECT game_id, GROUP_CONCAT(id) AS ids, COUNT(*) AS c
        FROM v156_reputation_subjects
        WHERE IFNULL(TRIM(game_id), '') != ''
        GROUP BY game_id
        HAVING c > 1
        ORDER BY c DESC, game_id
        LIMIT 50
        """
    ).fetchall()

    for g in game_id_groups:
        ids = [int(x) for x in (g["ids"] or "").split(",") if x.strip().isdigit()]
        groups.append(
            {
                "group_type": "game_id",
                "group_label": "游戏编号重复",
                "group_key": g["game_id"],
                "count": int(g["c"] or 0),
                "rows": _v156_subject_ids_to_rows(conn, ids),
            }
        )

    name_groups = conn.execute(
        """
        SELECT display_name, GROUP_CONCAT(id) AS ids, COUNT(*) AS c
        FROM v156_reputation_subjects
        WHERE IFNULL(TRIM(display_name), '') != ''
        GROUP BY display_name
        HAVING c > 1
        ORDER BY c DESC, display_name
        LIMIT 50
        """
    ).fetchall()

    for g in name_groups:
        ids = [int(x) for x in (g["ids"] or "").split(",") if x.strip().isdigit()]
        groups.append(
            {
                "group_type": "display_name",
                "group_label": "显示名称重复",
                "group_key": g["display_name"],
                "count": int(g["c"] or 0),
                "rows": _v156_subject_ids_to_rows(conn, ids),
            }
        )

    duplicate_subject_ids = set()

    for group in groups:
        for row in group["rows"]:
            duplicate_subject_ids.add(int(row["id"]))

    return {
        "groups": groups,
        "group_count": len(groups),
        "duplicate_subject_count": len(duplicate_subject_ids),
    }


def _v156_split_aliases(value: str | None) -> list[str]:
    if not value:
        return []

    raw = (
        value.replace("，", ",")
        .replace("、", ",")
        .replace("；", ",")
        .replace(";", ",")
        .split(",")
    )

    result = []

    for item in raw:
        item = item.strip()
        if item and item not in result:
            result.append(item)

    return result


def _v156_pick_worse_level(a: str | None, b: str | None, order: list[str]) -> str:
    a = (a or "").strip()
    b = (b or "").strip()

    rank = {name: i for i, name in enumerate(order)}

    if rank.get(b, -1) > rank.get(a, -1):
        return b

    return a or b


def merge_reputation_subjects(conn: sqlite3.Connection, keep_id: int, merge_id: int, *, battle_id: int | None=None) -> dict[str, Any]:
    ensure_reputation_tables(conn)
    ensure_reputation_merge_log_table(conn)
    if not keep_id or not merge_id:
        return {'ok': False, 'message': '缺少主体 ID。'}
    if keep_id == merge_id:
        return {'ok': False, 'message': '保留主体和被合并主体不能相同。'}
    keep = conn.execute('SELECT * FROM v156_reputation_subjects WHERE id=?', (keep_id,)).fetchone()
    merge = conn.execute('SELECT * FROM v156_reputation_subjects WHERE id=?', (merge_id,)).fetchone()
    if not keep or not merge:
        return {'ok': False, 'message': '主体不存在，无法合并。'}
    merge_relation_total = int(conn.execute('SELECT COUNT(*) FROM v156_reputation_event_relations WHERE subject_id=?', (merge_id,)).fetchone()[0] or 0)
    duplicate_relation_total = int(conn.execute('\n            SELECT COUNT(*)\n            FROM v156_reputation_event_relations mr\n            INNER JOIN v156_reputation_event_relations kr\n                ON kr.event_id = mr.event_id\n               AND kr.subject_id = ?\n            WHERE mr.subject_id = ?\n            ', (keep_id, merge_id)).fetchone()[0] or 0)
    moved_relation_total = max(0, merge_relation_total - duplicate_relation_total)
    keep_name = (keep['display_name'] or '').strip()
    merge_name = (merge['display_name'] or '').strip()
    alias_items: list[str] = []
    for item in _v156_split_aliases(keep['alias_names']):
        if item not in alias_items:
            alias_items.append(item)
    if merge_name and merge_name != keep_name and (merge_name not in alias_items):
        alias_items.append(merge_name)
    for item in _v156_split_aliases(merge['alias_names']):
        if item and item != keep_name and (item not in alias_items):
            alias_items.append(item)
    merged_alias_names = ','.join(alias_items)
    merged_game_id = (keep['game_id'] or '').strip() or (merge['game_id'] or '').strip()
    merged_trust_level = _v156_pick_worse_level(keep['trust_level'], merge['trust_level'], ['unknown', 'trusted', 'risky', 'black'])
    merged_risk_level = _v156_pick_worse_level(keep['risk_level'], merge['risk_level'], ['normal', 'warning', 'danger', 'black'])
    keep_note = (keep['note'] or '').strip()
    merge_note = (merge['note'] or '').strip()
    merge_info = f'已合并主体 #{merge_id}'
    if merge_name:
        merge_info += f'：{merge_name}'
    if merge['game_id']:
        merge_info += f"｜{merge['game_id']}"
    note_parts = [x for x in [keep_note, merge_note, merge_info] if x]
    merged_note = '\n\n'.join(note_parts)
    conn.execute('\n        UPDATE v156_reputation_event_relations\n        SET subject_id=?\n        WHERE subject_id=?\n          AND event_id NOT IN (\n              SELECT event_id\n              FROM v156_reputation_event_relations\n              WHERE subject_id=?\n          )\n        ', (keep_id, merge_id, keep_id))
    conn.execute('\n        DELETE FROM v156_reputation_event_relations\n        WHERE subject_id=?\n        ', (merge_id,))
    conn.execute("\n        UPDATE v156_reputation_subjects\n        SET\n            game_id=?,\n            alias_names=?,\n            trust_level=?,\n            risk_level=?,\n            note=?,\n            updated_at=datetime('now','localtime')\n        WHERE id=?\n        ", (merged_game_id, merged_alias_names, merged_trust_level, merged_risk_level, merged_note, keep_id))
    conn.execute('\n        DELETE FROM v156_reputation_subjects\n        WHERE id=?\n        ', (merge_id,))
    import json
    conn.execute("\n        INSERT INTO v156_reputation_merge_logs (battle_id,\n\n            keep_subject_id,\n            keep_display_name,\n            keep_game_id,\n            merge_subject_id,\n            merge_display_name,\n            merge_game_id,\n            moved_relations_count,\n            removed_duplicate_relations_count,\n            keep_snapshot,\n            merge_snapshot,\n            result_message,\n            created_at\n        )\n        VALUES (?,\n?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))\n        ", (battle_id, keep_id, keep_name, merged_game_id, merge_id, merge_name, (merge['game_id'] or '').strip(), moved_relation_total, duplicate_relation_total, json.dumps(dict(keep), ensure_ascii=False), json.dumps(dict(merge), ensure_ascii=False), f'已合并主体 #{merge_id} 到 #{keep_id}'))
    conn.commit()
    return {'ok': True, 'message': f'已合并主体 #{merge_id} 到 #{keep_id}。', 'keep_id': keep_id, 'merge_id': merge_id}


# =========================
# V15.6-A12 reputation merge audit logs
# =========================

def ensure_reputation_merge_log_table(conn: sqlite3.Connection) -> None:
    conn.execute('\n        CREATE TABLE IF NOT EXISTS v156_reputation_merge_logs (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            battle_id INTEGER,\n            keep_subject_id INTEGER,\n            keep_display_name TEXT,\n            keep_game_id TEXT,\n            merge_subject_id INTEGER,\n            merge_display_name TEXT,\n            merge_game_id TEXT,\n            moved_relations_count INTEGER DEFAULT 0,\n            removed_duplicate_relations_count INTEGER DEFAULT 0,\n            keep_snapshot TEXT,\n            merge_snapshot TEXT,\n            result_message TEXT,\n            created_at TEXT\n        )\n        ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_v156_reputation_merge_logs_battle_id\n        ON v156_reputation_merge_logs(battle_id)\n        ')
    conn.commit()


def list_reputation_merge_logs(
    conn: sqlite3.Connection,
    limit: int = 100,
) -> list:
    ensure_reputation_merge_log_table(conn)

    return conn.execute(
        """
        SELECT *
        FROM v156_reputation_merge_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


# =========================
# V15.6-A13 reputation subject delete protection
# =========================

def get_reputation_subject_relation_count(
    conn: sqlite3.Connection,
    subject_id: int,
) -> int:
    ensure_reputation_tables(conn)

    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM v156_reputation_event_relations
        WHERE subject_id=?
        """,
        (subject_id,),
    ).fetchone()

    return int(row[0] or 0) if row else 0


def delete_reputation_subject_safely(
    conn: sqlite3.Connection,
    subject_id: int,
) -> dict[str, Any]:
    ensure_reputation_tables(conn)

    subject = conn.execute(
        """
        SELECT id, display_name, game_id
        FROM v156_reputation_subjects
        WHERE id=?
        """,
        (subject_id,),
    ).fetchone()

    if not subject:
        return {
            "ok": False,
            "blocked": False,
            "message": "主体不存在，无法删除。",
        }

    relation_count = get_reputation_subject_relation_count(conn, subject_id)

    # V15.6-A13.1 first relation event guide
    first_event = conn.execute(
        """
        SELECT event_id
        FROM v156_reputation_event_relations
        WHERE subject_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (subject_id,),
    ).fetchone()

    first_event_id = int(first_event["event_id"] or 0) if first_event else 0

    if relation_count > 0:
        return {
            "ok": False,
            "blocked": True,
            "subject_id": subject_id,
            "display_name": subject["display_name"] or "",
            "game_id": subject["game_id"] or "",
            "relation_count": relation_count,
            "first_event_id": first_event_id,
            "message": f"该主体存在 {relation_count} 条事件关联，禁止直接删除。请先解除关联或通过合并机制处理。",
        }

    conn.execute(
        """
        DELETE FROM v156_reputation_subjects
        WHERE id=?
        """,
        (subject_id,),
    )

    conn.commit()

    return {
        "ok": True,
        "blocked": False,
        "subject_id": subject_id,
        "display_name": subject["display_name"] or "",
        "game_id": subject["game_id"] or "",
        "relation_count": 0,
        "message": "主体已删除。",
    }


# =========================
# V15.6-A14 reputation event delete protection
# =========================

def get_reputation_event_relation_count(
    conn: sqlite3.Connection,
    event_id: int,
) -> int:
    ensure_reputation_tables(conn)

    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM v156_reputation_event_relations
        WHERE event_id=?
        """,
        (event_id,),
    ).fetchone()

    return int(row[0] or 0) if row else 0


def delete_reputation_event_safely(
    conn: sqlite3.Connection,
    event_id: int,
) -> dict[str, Any]:
    ensure_reputation_tables(conn)

    event = conn.execute(
        """
        SELECT id, title, event_type, impact_level, status
        FROM v156_reputation_events
        WHERE id=?
        """,
        (event_id,),
    ).fetchone()

    if not event:
        return {
            "ok": False,
            "blocked": False,
            "message": "事件不存在，无法删除。",
        }

    relation_count = get_reputation_event_relation_count(conn, event_id)

    if relation_count > 0:
        return {
            "ok": False,
            "blocked": True,
            "event_id": event_id,
            "title": event["title"] or "",
            "relation_count": relation_count,
            "message": f"该事件存在 {relation_count} 条主体关联，禁止直接删除。请先解除关联，或保留事件作为证据记录。",
        }

    conn.execute(
        """
        DELETE FROM v156_reputation_events
        WHERE id=?
        """,
        (event_id,),
    )

    conn.commit()

    return {
        "ok": True,
        "blocked": False,
        "event_id": event_id,
        "title": event["title"] or "",
        "relation_count": 0,
        "message": "事件已删除。",
    }


# =========================
# V15.6-A15 reputation event status quick actions
# =========================

def update_reputation_event_status_quick(
    conn: sqlite3.Connection,
    event_id: int,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    ensure_reputation_tables(conn)

    status = (status or "").strip()
    note = (note or "").strip()

    allowed_status = {
        "recorded": "记录中",
        "pending": "待核实",
        "voided": "已作废",
        "resolved": "已处理",
    }

    if status not in allowed_status:
        return {
            "ok": False,
            "message": "不支持的事件状态。",
        }

    event = conn.execute(
        """
        SELECT *
        FROM v156_reputation_events
        WHERE id=?
        """,
        (event_id,),
    ).fetchone()

    if not event:
        return {
            "ok": False,
            "message": "事件不存在。",
        }

    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(v156_reputation_events)").fetchall()
    }

    update_fields = []
    values = []

    if "status" in cols:
        update_fields.append("status=?")
        values.append(status)

    if note and "evidence_note" in cols:
        old_note = event["evidence_note"] or ""
        new_note = old_note.strip()
        append_note = f"状态变更：{allowed_status[status]}｜{note}"

        if new_note:
            new_note = new_note + "\n\n" + append_note
        else:
            new_note = append_note

        update_fields.append("evidence_note=?")
        values.append(new_note)

    elif note and "note" in cols:
        old_note = event["note"] or ""
        new_note = old_note.strip()
        append_note = f"状态变更：{allowed_status[status]}｜{note}"

        if new_note:
            new_note = new_note + "\n\n" + append_note
        else:
            new_note = append_note

        update_fields.append("note=?")
        values.append(new_note)

    if "updated_at" in cols:
        update_fields.append("updated_at=datetime('now','localtime')")

    if not update_fields:
        return {
            "ok": False,
            "message": "事件表缺少可更新字段。",
        }

    values.append(event_id)

    conn.execute(
        f"""
        UPDATE v156_reputation_events
        SET {", ".join(update_fields)}
        WHERE id=?
        """,
        values,
    )

    conn.commit()

    return {
        "ok": True,
        "event_id": event_id,
        "status": status,
        "status_label": allowed_status[status],
        "message": f"事件状态已更新为：{allowed_status[status]}。",
    }


# =========================
# V15.7-A6 reputation risk workbench
# =========================

def build_reputation_workbench_report(
    conn: sqlite3.Connection,
    limit_per_priority: int = 50,
) -> dict[str, Any]:
    from urllib.parse import quote

    ensure_reputation_tables(conn)

    # V15.7-A6B shared workbench return context
    workbench_return = quote(
        "/reputation/workbench",
        safe="",
    )

    priority_rank = {
        "P1": 1,
        "P2": 2,
        "P3": 3,
    }

    items: dict[tuple[str, int], dict[str, Any]] = {}

    def add_item(
        *,
        priority: str,
        score: int,
        object_type: str,
        object_id: int,
        name: str,
        identifier: str,
        reason: str,
        evidence_state: str,
        evidence: str,
        action: str,
        detail_href: str,
        action_href: str,
        action_label: str,
        updated_at: str,
    ) -> None:
        key = (object_type, object_id)

        item = {
            "priority": priority,
            "score": score,
            "object_type": object_type,
            "object_label": (
                "信誉主体"
                if object_type == "subject"
                else "信誉事件"
            ),
            "object_id": object_id,
            "name": name or "未命名对象",
            "identifier": identifier or "-",
            "reason": reason,
            "evidence_state": evidence_state,
            "evidence": evidence,
            "action": action,
            "detail_href": detail_href,
            "action_href": action_href,
            "action_label": action_label,
            "updated_at": updated_at or "",
        }

        current = items.get(key)

        if current is None:
            items[key] = item
            return

        if priority_rank[priority] < priority_rank[current["priority"]]:
            items[key] = item
            return

        if (
            priority == current["priority"]
            and score > int(current.get("score") or 0)
        ):
            items[key] = item

    subject_rows = conn.execute(
        """
        SELECT
            s.*,
            COUNT(DISTINCT r.event_id) AS event_count,
            COUNT(
                DISTINCT CASE
                    WHEN e.impact_level IN (
                        'high',
                        'severe',
                        'critical'
                    )
                    THEN e.id
                END
            ) AS high_impact_count,
            COUNT(
                DISTINCT CASE
                    WHEN e.impact_level IN (
                        'severe',
                        'critical'
                    )
                    THEN e.id
                END
            ) AS severe_event_count,
            COUNT(
                DISTINCT CASE
                    WHEN e.status = 'verified'
                    THEN e.id
                END
            ) AS verified_event_count,
            COUNT(
                DISTINCT CASE
                    WHEN e.status = 'disputed'
                    THEN e.id
                END
            ) AS disputed_event_count,
            COUNT(
                DISTINCT CASE
                    WHEN e.impact_level IN (
                        'severe',
                        'critical'
                    )
                    AND e.status = 'verified'
                    THEN e.id
                END
            ) AS severe_verified_count
        FROM v156_reputation_subjects s
        LEFT JOIN v156_reputation_event_relations r
            ON r.subject_id = s.id
        LEFT JOIN v156_reputation_events e
            ON e.id = r.event_id
        GROUP BY s.id
        ORDER BY s.updated_at DESC, s.id DESC
        """
    ).fetchall()

    for row in subject_rows:
        subject_id = int(row["id"])
        status = (row["status"] or "").strip()

        if status in ("ignored", "archived"):
            continue

        display_name = (
            row["display_name"]
            or row["game_id"]
            or f"主体 #{subject_id}"
        )
        game_id = (row["game_id"] or "").strip()
        trust_level = (row["trust_level"] or "").strip()
        risk_level = (row["risk_level"] or "").strip()
        updated_at = row["updated_at"] or ""

        event_count = int(row["event_count"] or 0)
        high_impact_count = int(
            row["high_impact_count"] or 0
        )
        severe_event_count = int(
            row["severe_event_count"] or 0
        )
        verified_event_count = int(
            row["verified_event_count"] or 0
        )
        disputed_event_count = int(
            row["disputed_event_count"] or 0
        )
        severe_verified_count = int(
            row["severe_verified_count"] or 0
        )

        black_mark = (
            risk_level == "black"
            or trust_level in ("black", "blacklist")
        )

        high_risk_mark = (
            risk_level == "danger"
            or trust_level == "risky"
        )

        warning_mark = risk_level == "warning"

        evidence_state = (
            "完整"
            if event_count > 0
            else "缺失"
        )

        # V15.7-A6B workbench return context links
        subject_detail = (
            f"/reputation/subjects/{subject_id}"
            f"?return_to={workbench_return}"
        )
        subject_edit = (
            f"/reputation/subjects/{subject_id}/edit"
            f"?return_to={workbench_return}"
        )

        search_keyword = game_id or display_name
        search_href = (
            "/reputation/search?q="
            + quote(str(search_keyword))
        )

        if black_mark:
            add_item(
                priority="P1",
                score=100,
                object_type="subject",
                object_id=subject_id,
                name=display_name,
                identifier=game_id,
                reason="主体已被标记为黑名单",
                evidence_state=evidence_state,
                evidence=(
                    f"关联事件 {event_count} 条；"
                    f"严重事件 {severe_event_count} 条；"
                    f"已核实事件 {verified_event_count} 条"
                ),
                action=(
                    "暂停直接吸纳、回流和关键资源分配，"
                    "优先人工复核主体身份与历史事件。"
                ),
                detail_href=subject_detail,
                action_href=subject_detail,
                action_label="查看综合研判",
                updated_at=updated_at,
            )

        elif high_risk_mark and event_count == 0:
            add_item(
                priority="P1",
                score=97,
                object_type="subject",
                object_id=subject_id,
                name=display_name,
                identifier=game_id,
                reason="高风险主体尚无关联事件",
                evidence_state="缺失",
                evidence=(
                    "主体已有危险或存疑标记，"
                    "但当前关联事件为 0 条"
                ),
                action=(
                    "优先补充事件证据和责任关系，"
                    "证据补齐前不得直接放行。"
                ),
                detail_href=subject_detail,
                action_href=search_href,
                action_label="补充关联证据",
                updated_at=updated_at,
            )

        elif high_risk_mark and severe_verified_count > 0:
            add_item(
                priority="P1",
                score=95,
                object_type="subject",
                object_id=subject_id,
                name=display_name,
                identifier=game_id,
                reason="高风险标记已被严重核实事件印证",
                evidence_state="较强",
                evidence=(
                    f"已核实严重事件 "
                    f"{severe_verified_count} 条；"
                    f"全部关联事件 {event_count} 条"
                ),
                action=(
                    "纳入重点风险管理，后续吸纳、合作或"
                    "回流必须经过管理层人工确认。"
                ),
                detail_href=subject_detail,
                action_href=subject_detail,
                action_label="查看综合研判",
                updated_at=updated_at,
            )

        elif high_risk_mark:
            add_item(
                priority="P2",
                score=86,
                object_type="subject",
                object_id=subject_id,
                name=display_name,
                identifier=game_id,
                reason="主体存在危险或存疑标记",
                evidence_state=evidence_state,
                evidence=(
                    f"关联事件 {event_count} 条；"
                    f"高影响事件 {high_impact_count} 条；"
                    f"争议事件 {disputed_event_count} 条"
                ),
                action=(
                    "核对游戏编号、曾用名和全部关联事件，"
                    "形成稳定结论前保持观察。"
                ),
                detail_href=subject_detail,
                action_href=subject_detail,
                action_label="进入风险复核",
                updated_at=updated_at,
            )

        elif severe_verified_count > 0:
            add_item(
                priority="P2",
                score=83,
                object_type="subject",
                object_id=subject_id,
                name=display_name,
                identifier=game_id,
                reason="主体关联了已核实的严重事件",
                evidence_state="较强",
                evidence=(
                    f"已核实严重事件 "
                    f"{severe_verified_count} 条"
                ),
                action=(
                    "核对主体在严重事件中的责任角色，"
                    "必要时调整主体风险等级。"
                ),
                detail_href=subject_detail,
                action_href=subject_detail,
                action_label="查看严重事件",
                updated_at=updated_at,
            )

        elif disputed_event_count > 0 and verified_event_count == 0:
            add_item(
                priority="P2",
                score=80,
                object_type="subject",
                object_id=subject_id,
                name=display_name,
                identifier=game_id,
                reason="关联事件仍以争议记录为主",
                evidence_state="待复核",
                evidence=(
                    f"争议事件 {disputed_event_count} 条；"
                    "已核实事件 0 条"
                ),
                action=(
                    "补充不同来源证据与反证，"
                    "争议结束前暂不形成最终风险结论。"
                ),
                detail_href=subject_detail,
                action_href=subject_detail,
                action_label="查看争议记录",
                updated_at=updated_at,
            )

        elif high_impact_count > 0 and verified_event_count == 0:
            add_item(
                priority="P2",
                score=77,
                object_type="subject",
                object_id=subject_id,
                name=display_name,
                identifier=game_id,
                reason="存在高影响事件但缺少核实结论",
                evidence_state="待核实",
                evidence=(
                    f"高影响事件 {high_impact_count} 条；"
                    "已核实事件 0 条"
                ),
                action=(
                    "优先核实高影响事件的证据、状态和"
                    "主体责任关系。"
                ),
                detail_href=subject_detail,
                action_href=subject_detail,
                action_label="进入证据复核",
                updated_at=updated_at,
            )

        elif warning_mark and event_count == 0:
            add_item(
                priority="P3",
                score=68,
                object_type="subject",
                object_id=subject_id,
                name=display_name,
                identifier=game_id,
                reason="预警主体缺少关联事件",
                evidence_state="缺失",
                evidence="主体处于预警状态，但关联事件为 0 条",
                action=(
                    "补充至少一条可核实事件，"
                    "证据不足时仅保留观察。"
                ),
                detail_href=subject_detail,
                action_href=search_href,
                action_label="补充关联事件",
                updated_at=updated_at,
            )

        elif not game_id:
            add_item(
                priority="P3",
                score=63,
                object_type="subject",
                object_id=subject_id,
                name=display_name,
                identifier="-",
                reason="主体游戏编号缺失",
                evidence_state=evidence_state,
                evidence=(
                    "缺少唯一游戏编号，存在同名或身份"
                    "误判风险"
                ),
                action=(
                    "补充游戏编号并核对曾用名，"
                    "避免跨赛季检索时识别错误。"
                ),
                detail_href=subject_detail,
                action_href=subject_edit,
                action_label="完善主体资料",
                updated_at=updated_at,
            )

        elif warning_mark:
            add_item(
                priority="P3",
                score=58,
                object_type="subject",
                object_id=subject_id,
                name=display_name,
                identifier=game_id,
                reason="主体处于预警观察状态",
                evidence_state=evidence_state,
                evidence=(
                    f"关联事件 {event_count} 条；"
                    f"高影响事件 {high_impact_count} 条"
                ),
                action=(
                    "继续观察并补充后续记录，"
                    "出现新严重证据时再升级风险。"
                ),
                detail_href=subject_detail,
                action_href=subject_detail,
                action_label="查看主体档案",
                updated_at=updated_at,
            )

    event_rows = conn.execute(
        """
        SELECT
            e.*,
            COUNT(DISTINCT s.id) AS subject_count,
            COUNT(
                DISTINCT CASE
                    WHEN s.risk_level IN (
                        'danger',
                        'black'
                    )
                    OR s.trust_level IN (
                        'risky',
                        'black',
                        'blacklist'
                    )
                    THEN s.id
                END
            ) AS high_risk_subject_count
        FROM v156_reputation_events e
        LEFT JOIN v156_reputation_event_relations r
            ON r.event_id = e.id
        LEFT JOIN v156_reputation_subjects s
            ON s.id = r.subject_id
        GROUP BY e.id
        ORDER BY e.updated_at DESC, e.id DESC
        """
    ).fetchall()

    for row in event_rows:
        event_id = int(row["id"])
        status = (row["status"] or "").strip()

        if status in ("voided", "archived", "resolved"):
            continue

        title = row["title"] or f"事件 #{event_id}"
        impact_level = (row["impact_level"] or "").strip()
        updated_at = row["updated_at"] or ""

        subject_count = int(row["subject_count"] or 0)
        high_risk_subject_count = int(
            row["high_risk_subject_count"] or 0
        )

        severe = impact_level in ("severe", "critical")
        high_impact = impact_level in (
            "high",
            "severe",
            "critical",
        )

        evidence_state = (
            "完整"
            if subject_count > 0
            else "缺失"
        )

        event_detail = (
            f"/reputation/events/{event_id}"
            f"?return_to={workbench_return}"
        )
        event_edit = (
            f"/reputation/events/{event_id}/edit"
            f"?return_to={workbench_return}"
        )

        if severe and subject_count == 0:
            add_item(
                priority="P1",
                score=99,
                object_type="event",
                object_id=event_id,
                name=title,
                identifier=f"事件 #{event_id}",
                reason="严重事件尚未关联责任主体",
                evidence_state="缺失",
                evidence=(
                    "事件影响等级为严重或极严重，"
                    "但关联主体为 0 个"
                ),
                action=(
                    "立即补充责任主体和关联角色，"
                    "证据链补齐前不得形成最终处置。"
                ),
                detail_href=event_detail,
                action_href=event_edit,
                action_label="补充关联主体",
                updated_at=updated_at,
            )

        elif severe and status == "verified":
            add_item(
                priority="P1",
                score=96,
                object_type="event",
                object_id=event_id,
                name=title,
                identifier=f"事件 #{event_id}",
                reason="严重事件已经完成核实",
                evidence_state=evidence_state,
                evidence=(
                    f"已关联主体 {subject_count} 个；"
                    f"其中高风险主体 "
                    f"{high_risk_subject_count} 个"
                ),
                action=(
                    "优先查看关联主体责任，"
                    "并将事件纳入后续招募和管理决策。"
                ),
                detail_href=event_detail,
                action_href=event_detail,
                action_label="查看影响评估",
                updated_at=updated_at,
            )

        elif severe:
            add_item(
                priority="P2",
                score=89,
                object_type="event",
                object_id=event_id,
                name=title,
                identifier=f"事件 #{event_id}",
                reason="严重事件尚未完成最终核实",
                evidence_state=evidence_state,
                evidence=(
                    f"当前状态：{status or '未设置'}；"
                    f"关联主体 {subject_count} 个"
                ),
                action=(
                    "优先核对证据、责任主体和处理状态，"
                    "完成后再决定是否升级处置。"
                ),
                detail_href=event_detail,
                action_href=event_edit,
                action_label="进入事件核实",
                updated_at=updated_at,
            )

        elif status == "disputed":
            add_item(
                priority="P2",
                score=85,
                object_type="event",
                object_id=event_id,
                name=title,
                identifier=f"事件 #{event_id}",
                reason="事件处于争议状态",
                evidence_state="待复核",
                evidence=(
                    f"已关联主体 {subject_count} 个；"
                    "当前结论仍有争议"
                ),
                action=(
                    "补充不同来源证据、反证和双方陈述，"
                    "暂不作为单一最终依据。"
                ),
                detail_href=event_detail,
                action_href=event_edit,
                action_label="处理争议事件",
                updated_at=updated_at,
            )

        elif high_impact and subject_count == 0:
            add_item(
                priority="P2",
                score=82,
                object_type="event",
                object_id=event_id,
                name=title,
                identifier=f"事件 #{event_id}",
                reason="高影响事件缺少关联主体",
                evidence_state="缺失",
                evidence=(
                    "事件影响等级较高，"
                    "但尚未建立主体责任关系"
                ),
                action=(
                    "补充相关主体、责任角色和关联备注，"
                    "形成可追溯证据链。"
                ),
                detail_href=event_detail,
                action_href=event_edit,
                action_label="补充责任关系",
                updated_at=updated_at,
            )

        elif high_impact:
            add_item(
                priority="P2",
                score=76,
                object_type="event",
                object_id=event_id,
                name=title,
                identifier=f"事件 #{event_id}",
                reason="事件属于高影响记录",
                evidence_state=evidence_state,
                evidence=(
                    f"已关联主体 {subject_count} 个；"
                    f"高风险主体 "
                    f"{high_risk_subject_count} 个"
                ),
                action=(
                    "复核证据完整度和主体责任，"
                    "必要时调整事件状态或主体风险等级。"
                ),
                detail_href=event_detail,
                action_href=event_detail,
                action_label="查看影响评估",
                updated_at=updated_at,
            )

        elif subject_count == 0:
            add_item(
                priority="P3",
                score=67,
                object_type="event",
                object_id=event_id,
                name=title,
                identifier=f"事件 #{event_id}",
                reason="普通事件尚未关联主体",
                evidence_state="缺失",
                evidence="当前关联主体为 0 个",
                action=(
                    "补充涉及主体和责任关系，"
                    "避免事件成为孤立记录。"
                ),
                detail_href=event_detail,
                action_href=event_edit,
                action_label="补充关联主体",
                updated_at=updated_at,
            )

        elif status in ("pending", "recorded"):
            add_item(
                priority="P3",
                score=61,
                object_type="event",
                object_id=event_id,
                name=title,
                identifier=f"事件 #{event_id}",
                reason="事件仍处于待核实或记录中",
                evidence_state=evidence_state,
                evidence=f"当前已关联主体 {subject_count} 个",
                action=(
                    "继续补充证据备注，"
                    "确认后更新为已核实或其他最终状态。"
                ),
                detail_href=event_detail,
                action_href=event_edit,
                action_label="完善事件状态",
                updated_at=updated_at,
            )

    queues = {
        "P1": [],
        "P2": [],
        "P3": [],
    }

    for item in items.values():
        queues[item["priority"]].append(item)

    for priority in queues:
        queues[priority].sort(
            key=lambda item: (
                int(item.get("score") or 0),
                item.get("updated_at") or "",
                int(item.get("object_id") or 0),
            ),
            reverse=True,
        )

    raw_counts = {
        priority: len(queue)
        for priority, queue in queues.items()
    }

    shown_queues = {
        priority: queue[:limit_per_priority]
        for priority, queue in queues.items()
    }

    all_items = [
        item
        for queue in queues.values()
        for item in queue
    ]

    # V15.7-A7-2 workbench task integration
    active_task_map = get_active_reputation_task_map(
        conn
    )

    active_task_count = 0

    for item in all_items:
        task_key = (
            item["object_type"],
            int(item["object_id"]),
        )

        active_task = active_task_map.get(
            task_key
        )

        item["active_task"] = active_task

        if active_task:
            active_task_count += 1

    subject_task_count = sum(
        1
        for item in all_items
        if item["object_type"] == "subject"
    )

    event_task_count = sum(
        1
        for item in all_items
        if item["object_type"] == "event"
    )

    generated_row = conn.execute(
        "SELECT datetime('now','localtime')"
    ).fetchone()

    generated_at = (
        generated_row[0]
        if generated_row
        else ""
    )

    return {
        "stats": {
            "total_count": len(all_items),
            "p1_count": raw_counts["P1"],
            "p2_count": raw_counts["P2"],
            "p3_count": raw_counts["P3"],
            "subject_count": subject_task_count,
            "event_count": event_task_count,
            "active_task_count": active_task_count,
        },
        "raw_counts": raw_counts,
        "queues": shown_queues,
        "limit_per_priority": limit_per_priority,
        "generated_at": generated_at,
    }


# =========================
# V15.7-A7-1 reputation task storage
# =========================

_REPUTATION_TASK_ENTITY_TYPES = {
    "subject",
    "event",
}

_REPUTATION_TASK_PRIORITIES = {
    "P1",
    "P2",
    "P3",
}

_REPUTATION_TASK_STATUSES = {
    "pending",
    "processing",
    "completed",
    "ignored",
}

_REPUTATION_TASK_ACTIVE_STATUSES = {
    "pending",
    "processing",
}

_REPUTATION_TASK_CLOSED_STATUSES = {
    "completed",
    "ignored",
}


def _get_reputation_task_entity_snapshot(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
) -> dict[str, Any] | None:
    if entity_type == "subject":
        row = conn.execute(
            """
            SELECT
                id,
                display_name,
                game_id
            FROM v156_reputation_subjects
            WHERE id=?
            """,
            (entity_id,),
        ).fetchone()

        if not row:
            return None

        return {
            "entity_name": (
                row["display_name"]
                or row["game_id"]
                or f"主体 #{entity_id}"
            ),
            "entity_identifier": (
                row["game_id"]
                or f"主体 #{entity_id}"
            ),
        }

    if entity_type == "event":
        row = conn.execute(
            """
            SELECT
                id,
                title
            FROM v156_reputation_events
            WHERE id=?
            """,
            (entity_id,),
        ).fetchone()

        if not row:
            return None

        return {
            "entity_name": (
                row["title"]
                or f"事件 #{entity_id}"
            ),
            "entity_identifier": (
                f"事件 #{entity_id}"
            ),
        }

    return None


def create_reputation_task(conn: sqlite3.Connection, data: dict[str, Any], *, battle_id=None) -> dict[str, Any]:
    if battle_id is not None:
        battle_id = _v155_reputation_positive_battle_id(battle_id)
    ensure_reputation_tables(conn)
    entity_type = (data.get('entity_type') or '').strip().lower()
    try:
        entity_id = int(data.get('entity_id') or 0)
    except Exception:
        entity_id = 0
    priority = (data.get('priority') or 'P3').strip().upper()
    task_reason = (data.get('task_reason') or '').strip()
    recommended_action = (data.get('recommended_action') or '').strip()
    owner = (data.get('owner') or '').strip()
    source_type = (data.get('source_type') or 'workbench').strip()
    if entity_type not in _REPUTATION_TASK_ENTITY_TYPES:
        return {'ok': False, 'message': '任务对象类型无效。'}
    if entity_id <= 0:
        return {'ok': False, 'message': '任务对象编号无效。'}
    if priority not in _REPUTATION_TASK_PRIORITIES:
        return {'ok': False, 'message': '任务优先级无效。'}
    if not task_reason:
        return {'ok': False, 'message': '任务风险原因不能为空。'}
    snapshot = _get_reputation_task_entity_snapshot(conn, entity_type, entity_id)
    if not snapshot:
        return {'ok': False, 'not_found': True, 'message': '任务对应的主体或事件不存在。'}
    existing = conn.execute("\n        SELECT\n            id,\n            status\n        FROM v157_reputation_tasks\n        WHERE entity_type=?\n          AND entity_id=?\n          AND status IN (\n              'pending',\n              'processing'\n          )\n        ORDER BY id DESC\n        LIMIT 1\n        ", (entity_type, entity_id)).fetchone()
    if existing:
        return {'ok': False, 'duplicate': True, 'task_id': int(existing['id']), 'status': existing['status'], 'message': '该对象已有未闭环处置任务。'}
    try:
        cursor = conn.execute("\n            INSERT INTO v157_reputation_tasks (\n                battle_id,\n            entity_type,\n                entity_id,\n                entity_name,\n                entity_identifier,\n                priority,\n                task_reason,\n                recommended_action,\n                owner,\n                status,\n                result_note,\n                source_type,\n                updated_at,\n                completed_at\n            )\n            VALUES (\n                ?,\n            ?, ?, ?, ?, ?, ?, ?, ?,\n                'pending', '', ?,\n                datetime('now','localtime'),\n                ''\n            )\n            ", (battle_id,) + tuple((entity_type, entity_id, snapshot['entity_name'], snapshot['entity_identifier'], priority, task_reason, recommended_action, owner, source_type)))
        conn.commit()
    except sqlite3.IntegrityError:
        return {'ok': False, 'duplicate': True, 'message': '该对象已有未闭环处置任务。'}
    task_id = int(cursor.lastrowid)
    return {'ok': True, 'task_id': task_id, 'message': '处置任务已创建。'}


def get_reputation_task(
    conn: sqlite3.Connection,
    task_id: int,
):
    ensure_reputation_tables(conn)

    return conn.execute(
        """
        SELECT *
        FROM v157_reputation_tasks
        WHERE id=?
        """,
        (task_id,),
    ).fetchone()


def list_reputation_tasks(
    conn: sqlite3.Connection,
    *,
    status: str = "",
    priority: str = "",
    q: str = "",
    limit: int = 200,
) -> list:
    ensure_reputation_tables(conn)

    status = (status or "").strip().lower()
    priority = (priority or "").strip().upper()
    q = (q or "").strip()

    conditions = []
    params: list[Any] = []

    if status in _REPUTATION_TASK_STATUSES:
        conditions.append("status=?")
        params.append(status)

    if priority in _REPUTATION_TASK_PRIORITIES:
        conditions.append("priority=?")
        params.append(priority)

    if q:
        like = f"%{q}%"

        conditions.append(
            """
            (
                IFNULL(entity_name, '') LIKE ?
                OR IFNULL(entity_identifier, '') LIKE ?
                OR IFNULL(task_reason, '') LIKE ?
                OR IFNULL(recommended_action, '') LIKE ?
                OR IFNULL(owner, '') LIKE ?
                OR IFNULL(result_note, '') LIKE ?
            )
            """
        )

        params.extend(
            [
                like,
                like,
                like,
                like,
                like,
                like,
            ]
        )

    where_sql = ""

    if conditions:
        where_sql = (
            "WHERE "
            + " AND ".join(conditions)
        )

    params.append(max(1, int(limit or 200)))

    return conn.execute(
        f"""
        SELECT *
        FROM v157_reputation_tasks
        {where_sql}
        ORDER BY
            CASE
                WHEN status='processing' THEN 1
                WHEN status='pending' THEN 2
                WHEN status='completed' THEN 3
                WHEN status='ignored' THEN 4
                ELSE 9
            END,
            CASE
                WHEN priority='P1' THEN 1
                WHEN priority='P2' THEN 2
                WHEN priority='P3' THEN 3
                ELSE 9
            END,
            updated_at DESC,
            id DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()


def update_reputation_task(
    conn: sqlite3.Connection,
    task_id: int,
    data: dict[str, Any],
) -> dict[str, Any]:
    ensure_reputation_tables(conn)

    row = get_reputation_task(
        conn,
        task_id,
    )

    if not row:
        return {
            "ok": False,
            "not_found": True,
            "message": "处置任务不存在。",
        }

    priority = (
        data.get("priority")
        or row["priority"]
        or "P3"
    ).strip().upper()

    status = (
        data.get("status")
        or row["status"]
        or "pending"
    ).strip().lower()

    owner = (
        data.get("owner")
        if data.get("owner") is not None
        else row["owner"]
    )

    result_note = (
        data.get("result_note")
        if data.get("result_note") is not None
        else row["result_note"]
    )

    owner = (owner or "").strip()
    result_note = (result_note or "").strip()

    if priority not in _REPUTATION_TASK_PRIORITIES:
        return {
            "ok": False,
            "message": "任务优先级无效。",
        }

    if status not in _REPUTATION_TASK_STATUSES:
        return {
            "ok": False,
            "message": "任务状态无效。",
        }

    # V15.7-A7-3 task closure validation
    if len(owner) > 100:
        return {
            "ok": False,
            "message": "负责人名称不能超过100个字符。",
        }

    if len(result_note) > 2000:
        return {
            "ok": False,
            "message": "处置结果不能超过2000个字符。",
        }

    if (
        status in _REPUTATION_TASK_CLOSED_STATUSES
        and not result_note
    ):
        return {
            "ok": False,
            "result_required": True,
            "message": (
                "完成或忽略任务前，"
                "必须填写处置结果。"
            ),
        }

    try:
        if status in _REPUTATION_TASK_CLOSED_STATUSES:
            conn.execute(
                """
                UPDATE v157_reputation_tasks
                SET
                    priority=?,
                    owner=?,
                    status=?,
                    result_note=?,
                    updated_at=datetime(
                        'now',
                        'localtime'
                    ),
                    completed_at=CASE
                        WHEN IFNULL(
                            completed_at,
                            ''
                        )=''
                        THEN datetime(
                            'now',
                            'localtime'
                        )
                        ELSE completed_at
                    END
                WHERE id=?
                """,
                (
                    priority,
                    owner,
                    status,
                    result_note,
                    task_id,
                ),
            )

        else:
            conn.execute(
                """
                UPDATE v157_reputation_tasks
                SET
                    priority=?,
                    owner=?,
                    status=?,
                    result_note=?,
                    updated_at=datetime(
                        'now',
                        'localtime'
                    ),
                    completed_at=''
                WHERE id=?
                """,
                (
                    priority,
                    owner,
                    status,
                    result_note,
                    task_id,
                ),
            )

        conn.commit()

    except sqlite3.IntegrityError:
        return {
            "ok": False,
            "duplicate": True,
            "message": "该对象已经存在另一条未闭环任务。",
        }

    updated = get_reputation_task(
        conn,
        task_id,
    )

    return {
        "ok": True,
        "task": updated,
        "message": "处置任务已更新。",
    }


def build_reputation_task_report(
    conn: sqlite3.Connection,
    *,
    status: str = "",
    priority: str = "",
    q: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    ensure_reputation_tables(conn)

    rows = list_reputation_tasks(
        conn,
        status=status,
        priority=priority,
        q=q,
        limit=limit,
    )

    stat_row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(
                CASE
                    WHEN status='pending'
                    THEN 1
                    ELSE 0
                END
            ) AS pending_count,
            SUM(
                CASE
                    WHEN status='processing'
                    THEN 1
                    ELSE 0
                END
            ) AS processing_count,
            SUM(
                CASE
                    WHEN status='completed'
                    THEN 1
                    ELSE 0
                END
            ) AS completed_count,
            SUM(
                CASE
                    WHEN status='ignored'
                    THEN 1
                    ELSE 0
                END
            ) AS ignored_count,
            SUM(
                CASE
                    WHEN status IN (
                        'pending',
                        'processing'
                    )
                    THEN 1
                    ELSE 0
                END
            ) AS active_count,
            SUM(
                CASE
                    WHEN priority='P1'
                     AND status IN (
                         'pending',
                         'processing'
                     )
                    THEN 1
                    ELSE 0
                END
            ) AS p1_active_count
        FROM v157_reputation_tasks
        """
    ).fetchone()

    return {
        "rows": rows,
        "stats": {
            "total_count": int(
                stat_row["total_count"]
                or 0
            ),
            "pending_count": int(
                stat_row["pending_count"]
                or 0
            ),
            "processing_count": int(
                stat_row["processing_count"]
                or 0
            ),
            "completed_count": int(
                stat_row["completed_count"]
                or 0
            ),
            "ignored_count": int(
                stat_row["ignored_count"]
                or 0
            ),
            "active_count": int(
                stat_row["active_count"]
                or 0
            ),
            "p1_active_count": int(
                stat_row["p1_active_count"]
                or 0
            ),
        },
        "filters": {
            "status": (
                status
                if status
                in _REPUTATION_TASK_STATUSES
                else ""
            ),
            "priority": (
                priority
                if priority
                in _REPUTATION_TASK_PRIORITIES
                else ""
            ),
            "q": q or "",
        },
    }


# =========================
# V15.7-A7-2 workbench task actions
# =========================

def get_active_reputation_task_map(
    conn: sqlite3.Connection,
) -> dict[tuple[str, int], dict[str, Any]]:
    ensure_reputation_tables(conn)

    rows = conn.execute(
        """
        SELECT *
        FROM v157_reputation_tasks
        WHERE status IN (
            'pending',
            'processing'
        )
        ORDER BY updated_at DESC, id DESC
        """
    ).fetchall()

    result: dict[
        tuple[str, int],
        dict[str, Any],
    ] = {}

    for row in rows:
        entity_type = (
            row["entity_type"]
            or ""
        ).strip()

        try:
            entity_id = int(
                row["entity_id"]
                or 0
            )
        except Exception:
            entity_id = 0

        if (
            entity_type
            not in _REPUTATION_TASK_ENTITY_TYPES
            or entity_id <= 0
        ):
            continue

        key = (
            entity_type,
            entity_id,
        )

        if key not in result:
            result[key] = dict(row)

    return result


def create_reputation_task_from_workbench(conn: sqlite3.Connection, *, entity_type: str, entity_id: int, battle_id=None) -> dict[str, Any]:
    ensure_reputation_tables(conn)
    entity_type = (entity_type or '').strip().lower()
    try:
        entity_id = int(entity_id or 0)
    except Exception:
        entity_id = 0
    if entity_type not in _REPUTATION_TASK_ENTITY_TYPES:
        return {'ok': False, 'message': '工作台任务对象类型无效。'}
    if entity_id <= 0:
        return {'ok': False, 'message': '工作台任务对象编号无效。'}
    report = build_reputation_workbench_report(conn, limit_per_priority=5000)
    matched_item = None
    for priority in ('P1', 'P2', 'P3'):
        for item in report['queues'].get(priority, []):
            if item.get('object_type') == entity_type and int(item.get('object_id') or 0) == entity_id:
                matched_item = item
                break
        if matched_item:
            break
    if not matched_item:
        return {'ok': False, 'not_found': True, 'message': '该对象已经不在当前风险处置队列中，请刷新工作台后重新确认。'}
    return create_reputation_task(conn, {'entity_type': entity_type, 'entity_id': entity_id, 'priority': matched_item.get('priority') or 'P3', 'task_reason': matched_item.get('reason') or '', 'recommended_action': matched_item.get('action') or '', 'source_type': 'workbench'}, battle_id=battle_id)


# ============================================================
# V15.5-A5-P0-S07 battle-scoped reputation resource helpers
# Candidate only until explicit production source apply.
# ============================================================

def _v155_reputation_positive_battle_id(battle_id):
    try:
        value = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError("positive battle_id required")

    if value <= 0:
        raise ValueError("positive battle_id required")

    return value


def _v155_reputation_row_dict(row):
    if row is None:
        return None

    try:
        return dict(row)
    except Exception:
        return row


def _v155_reputation_rows_dict(rows):
    result = []

    for row in rows:
        try:
            result.append(dict(row))
        except Exception:
            result.append(row)

    return result























# ============================================================
# V15.5-A5-P0-S08 battle-scoped reputation helpers
# ============================================================









# ============================================================
# V15.5-A5-P0-S09 battle-scoped reputation read/report adapter
# ============================================================

class _V155S09BattleScopedConnection:
    _TENANT_TABLES = (
        "v156_reputation_subjects",
        "v156_reputation_events",
        "v156_reputation_event_relations",
        "v157_reputation_tasks",
        "v156_reputation_merge_logs",
    )

    def __init__(self, conn, battle_id: int):
        self._conn = conn
        self._battle_id = _v155_reputation_positive_battle_id(
            battle_id
        )

    def __getattr__(self, name):
        return getattr(self._conn, name)

    @staticmethod
    def _is_read_statement(sql: str) -> bool:
        text = str(sql or "").lstrip()
        return bool(
            re.match(
                r"^(SELECT|WITH)\b",
                text,
                flags=re.I,
            )
        )

    def _scope_select(self, sql: str, params=()):
        text = str(sql or "")

        if not self._is_read_statement(text):
            return text, params

        tables = [
            table
            for table in self._TENANT_TABLES
            if re.search(
                r"(?<![A-Za-z0-9_])"
                + re.escape(table)
                + r"(?![A-Za-z0-9_])",
                text,
                flags=re.I,
            )
        ]

        if not tables:
            return text, params

        stripped = text.lstrip()

        if re.match(
            r"^WITH\b",
            stripped,
            flags=re.I,
        ):
            raise RuntimeError(
                "P0-S09 scoped adapter refuses nested WITH "
                "without explicit review"
            )

        ctes = []

        for table in tables:
            ctes.append(
                f"{table} AS ("
                f"SELECT * FROM main.{table} "
                f"WHERE battle_id=?"
                f")"
            )

        scoped_sql = (
            "WITH "
            + ", ".join(ctes)
            + " "
            + stripped
        )

        if params is None:
            params = ()

        if isinstance(
            params,
            tuple,
        ):
            scoped_params = (
                tuple(
                    self._battle_id
                    for _ in tables
                )
                + params
            )

        elif isinstance(
            params,
            list,
        ):
            scoped_params = (
                [
                    self._battle_id
                    for _ in tables
                ]
                + params
            )

        else:
            raise TypeError(
                "P0-S09 scoped adapter only accepts "
                "positional tuple/list SQL bindings"
            )

        return (
            scoped_sql,
            scoped_params,
        )

    def execute(self, sql, params=()):
        scoped_sql, scoped_params = self._scope_select(
            sql,
            params,
        )

        return self._conn.execute(
            scoped_sql,
            scoped_params,
        )


def make_reputation_battle_scoped_connection(
    conn,
    battle_id: int,
):
    return _V155S09BattleScopedConnection(
        conn,
        battle_id,
    )










# =====================================================================
# REPUTATION_GLOBAL_KNOWLEDGE_MODEL_A4
#
# Ownership:
#   reputation knowledge -> workspace_id
#
# Context:
#   battle_id -> occurrence / event / operational context
#
# Compatibility:
#   existing public battle_id arguments are preserved.
# =====================================================================

_A4_REPUTATION_KNOWLEDGE_TABLES = (
    "v156_reputation_subjects",
    "v156_reputation_events",
    "v156_reputation_event_relations",
    "v156_reputation_merge_logs",
    "v156_reputation_subject_battles",
)

_A4_REPUTATION_OPERATIONAL_TABLES = (
    "v157_reputation_tasks",
)


def _v156_a4_base_conn(conn):
    return getattr(
        conn,
        "_conn",
        conn,
    )


def _v156_a4_workspace_id_for_battle(
    conn,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(
        battle_id
    )

    base = _v156_a4_base_conn(
        conn
    )

    row = base.execute(
        """
        SELECT workspace_id
        FROM v155_workspace_battles
        WHERE battle_id = ?
        LIMIT 1
        """,
        (
            battle_id,
        ),
    ).fetchone()

    if row is None:
        raise ValueError(
            "workspace mapping required for battle_id"
        )

    workspace_id = int(
        row[0]
    )

    if workspace_id <= 0:
        raise ValueError(
            "positive workspace_id required"
        )

    return workspace_id


def _v156_a4_link_subject_battle(
    conn,
    *,
    workspace_id,
    subject_id,
    battle_id,
    source_type="application",
):
    base = _v156_a4_base_conn(
        conn
    )

    base.execute(
        """
        INSERT OR IGNORE INTO
        v156_reputation_subject_battles (
            workspace_id,
            subject_id,
            battle_id,
            first_seen_at,
            last_seen_at,
            source_type,
            updated_at
        )
        VALUES (
            ?, ?, ?,
            datetime('now','localtime'),
            datetime('now','localtime'),
            ?,
            datetime('now','localtime')
        )
        """,
        (
            int(workspace_id),
            int(subject_id),
            int(battle_id),
            str(
                source_type
                or "application"
            ),
        ),
    )

    base.execute(
        """
        UPDATE
            v156_reputation_subject_battles
        SET
            last_seen_at =
                datetime('now','localtime'),
            updated_at =
                datetime('now','localtime')
        WHERE workspace_id = ?
          AND subject_id = ?
          AND battle_id = ?
        """,
        (
            int(workspace_id),
            int(subject_id),
            int(battle_id),
        ),
    )




def ensure_reputation_tables(
    conn,
):
    """
    A4 additive bootstrap.

    Existing populated pre-A3 databases fail closed instead of
    silently guessing workspace ownership.
    """
    base = _v156_a4_base_conn(
        conn
    )

    _a4_legacy_ensure_reputation_tables(
        base
    )

    try:
        ensure_reputation_merge_log_table(
            base
        )
    except NameError:
        pass

    scope_tables = (
        "v156_reputation_subjects",
        "v156_reputation_events",
        "v156_reputation_event_relations",
        "v156_reputation_merge_logs",
        "v157_reputation_tasks",
    )

    for table in scope_tables:

        columns = {
            str(row[1])
            for row in base.execute(
                'PRAGMA table_info("'
                + table
                + '")'
            ).fetchall()
        }

        if "workspace_id" in columns:
            continue

        row_count = int(
            base.execute(
                'SELECT COUNT(*) FROM "'
                + table
                + '"'
            ).fetchone()[0]
        )

        if row_count:
            raise RuntimeError(
                "A3 migration required before A4: "
                + table
            )

        base.execute(
            'ALTER TABLE "'
            + table
            + '" ADD COLUMN workspace_id INTEGER'
        )

    base.execute(
        """
        CREATE TABLE IF NOT EXISTS
        v156_reputation_subject_battles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            battle_id INTEGER NOT NULL,
            first_seen_at TEXT,
            last_seen_at TEXT,
            source_type TEXT NOT NULL
                DEFAULT 'application',
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (
                workspace_id,
                subject_id,
                battle_id
            )
        )
        """
    )

    index_sql = (
        """
        CREATE INDEX IF NOT EXISTS
        idx_v156_reputation_subjects_workspace
        ON v156_reputation_subjects(workspace_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS
        idx_v156_reputation_subjects_workspace_game
        ON v156_reputation_subjects(
            workspace_id,
            game_id
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS
        idx_v156_reputation_events_workspace
        ON v156_reputation_events(workspace_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS
        idx_v156_reputation_event_relations_workspace
        ON v156_reputation_event_relations(workspace_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS
        idx_v156_reputation_merge_logs_workspace
        ON v156_reputation_merge_logs(workspace_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS
        idx_v157_reputation_tasks_workspace
        ON v157_reputation_tasks(workspace_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS
        idx_v156_reputation_subject_battles_workspace
        ON v156_reputation_subject_battles(
            workspace_id
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS
        idx_v156_reputation_subject_battles_subject
        ON v156_reputation_subject_battles(
            workspace_id,
            subject_id
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS
        idx_v156_reputation_subject_battles_battle
        ON v156_reputation_subject_battles(
            workspace_id,
            battle_id
        )
        """,
    )

    for sql in index_sql:
        base.execute(sql)

    base.execute(
        """
        CREATE TRIGGER IF NOT EXISTS
        trg_rep_subject_workspace_bridge
        AFTER INSERT ON v156_reputation_subjects
        WHEN
            NEW.workspace_id IS NULL
            AND NEW.battle_id IS NOT NULL
        BEGIN
            UPDATE v156_reputation_subjects
            SET workspace_id = (
                SELECT workspace_id
                FROM v155_workspace_battles
                WHERE battle_id = NEW.battle_id
            )
            WHERE id = NEW.id;

            INSERT OR IGNORE INTO
            v156_reputation_subject_battles (
                workspace_id,
                subject_id,
                battle_id,
                first_seen_at,
                last_seen_at,
                source_type
            )
            SELECT
                workspace_id,
                NEW.id,
                NEW.battle_id,
                NEW.created_at,
                NEW.updated_at,
                'legacy_bridge'
            FROM v155_workspace_battles
            WHERE battle_id = NEW.battle_id;
        END
        """
    )

    base.execute(
        """
        CREATE TRIGGER IF NOT EXISTS
        trg_rep_event_workspace_bridge
        AFTER INSERT ON v156_reputation_events
        WHEN
            NEW.workspace_id IS NULL
            AND NEW.battle_id IS NOT NULL
        BEGIN
            UPDATE v156_reputation_events
            SET workspace_id = (
                SELECT workspace_id
                FROM v155_workspace_battles
                WHERE battle_id = NEW.battle_id
            )
            WHERE id = NEW.id;
        END
        """
    )

    base.execute(
        """
        CREATE TRIGGER IF NOT EXISTS
        trg_rep_relation_workspace_bridge
        AFTER INSERT ON v156_reputation_event_relations
        WHEN NEW.workspace_id IS NULL
        BEGIN
            UPDATE v156_reputation_event_relations
            SET workspace_id = COALESCE(
                (
                    SELECT workspace_id
                    FROM v155_workspace_battles
                    WHERE battle_id = NEW.battle_id
                ),
                (
                    SELECT workspace_id
                    FROM v156_reputation_subjects
                    WHERE id = NEW.subject_id
                ),
                (
                    SELECT workspace_id
                    FROM v156_reputation_events
                    WHERE id = NEW.event_id
                )
            )
            WHERE id = NEW.id;
        END
        """
    )

    base.execute(
        """
        CREATE TRIGGER IF NOT EXISTS
        trg_rep_merge_workspace_bridge
        AFTER INSERT ON v156_reputation_merge_logs
        WHEN
            NEW.workspace_id IS NULL
            AND NEW.battle_id IS NOT NULL
        BEGIN
            UPDATE v156_reputation_merge_logs
            SET workspace_id = (
                SELECT workspace_id
                FROM v155_workspace_battles
                WHERE battle_id = NEW.battle_id
            )
            WHERE id = NEW.id;
        END
        """
    )

    base.execute(
        """
        CREATE TRIGGER IF NOT EXISTS
        trg_rep_task_workspace_bridge
        AFTER INSERT ON v157_reputation_tasks
        WHEN NEW.workspace_id IS NULL
        BEGIN
            UPDATE v157_reputation_tasks
            SET workspace_id = COALESCE(
                (
                    SELECT workspace_id
                    FROM v155_workspace_battles
                    WHERE battle_id = NEW.battle_id
                ),
                (
                    SELECT workspace_id
                    FROM v156_reputation_subjects
                    WHERE
                        NEW.entity_type = 'subject'
                        AND id = NEW.entity_id
                ),
                (
                    SELECT workspace_id
                    FROM v156_reputation_events
                    WHERE
                        NEW.entity_type = 'event'
                        AND id = NEW.entity_id
                )
            )
            WHERE id = NEW.id;
        END
        """
    )

    base.commit()


class _V156A4WorkspaceScopedConnection:
    """
    Long-term knowledge boundary.

    Knowledge tables:
        workspace_id

    Task table:
        workspace_id + current battle_id
    """

    _TABLES = (
        "v156_reputation_subjects",
        "v156_reputation_events",
        "v156_reputation_event_relations",
        "v156_reputation_merge_logs",
        "v156_reputation_subject_battles",
        "v157_reputation_tasks",
    )

    def __init__(
        self,
        conn,
        battle_id,
    ):
        self._conn = _v156_a4_base_conn(
            conn
        )

        self._battle_id = (
            _v155_reputation_positive_battle_id(
                battle_id
            )
        )

        self._workspace_id = (
            _v156_a4_workspace_id_for_battle(
                self._conn,
                self._battle_id,
            )
        )

    def __getattr__(
        self,
        name,
    ):
        return getattr(
            self._conn,
            name,
        )

    @staticmethod
    def _is_read_statement(
        sql,
    ):
        return bool(
            re.match(
                r"^(SELECT|WITH)\b",
                str(sql or "").lstrip(),
                flags=re.I,
            )
        )

    def _scope_select(
        self,
        sql,
        params=(),
    ):
        text = str(
            sql or ""
        )

        if not self._is_read_statement(
            text
        ):
            return (
                text,
                params,
            )

        stripped = text.lstrip()

        if re.match(
            r"^WITH\b",
            stripped,
            flags=re.I,
        ):
            raise RuntimeError(
                "A4 workspace adapter refuses nested WITH "
                "without explicit review"
            )

        tables = [
            table
            for table in self._TABLES
            if re.search(
                r"(?<![A-Za-z0-9_])"
                + re.escape(table)
                + r"(?![A-Za-z0-9_])",
                text,
                flags=re.I,
            )
        ]

        if not tables:
            return (
                text,
                params,
            )

        ctes = []
        scope_params = []

        for table in tables:

            if (
                table
                == "v157_reputation_tasks"
            ):
                ctes.append(
                    table
                    + " AS ("
                    + "SELECT * FROM main."
                    + table
                    + " WHERE workspace_id=? "
                    + "AND battle_id=?"
                    + ")"
                )

                scope_params.extend(
                    [
                        self._workspace_id,
                        self._battle_id,
                    ]
                )

            else:
                ctes.append(
                    table
                    + " AS ("
                    + "SELECT * FROM main."
                    + table
                    + " WHERE workspace_id=?"
                    + ")"
                )

                scope_params.append(
                    self._workspace_id
                )

        scoped_sql = (
            "WITH "
            + ", ".join(ctes)
            + " "
            + stripped
        )

        if params is None:
            params = ()

        if isinstance(
            params,
            tuple,
        ):
            scoped_params = (
                tuple(scope_params)
                + params
            )

        elif isinstance(
            params,
            list,
        ):
            scoped_params = (
                list(scope_params)
                + params
            )

        else:
            raise TypeError(
                "A4 workspace adapter accepts "
                "tuple/list positional bindings only"
            )

        return (
            scoped_sql,
            scoped_params,
        )

    def execute(
        self,
        sql,
        params=(),
    ):
        sql2, params2 = (
            self._scope_select(
                sql,
                params,
            )
        )

        return self._conn.execute(
            sql2,
            params2,
        )


def make_reputation_workspace_scoped_connection(
    conn,
    battle_id,
):
    return _V156A4WorkspaceScopedConnection(
        conn,
        battle_id,
    )


class _V155S09BattleScopedConnection:
    _TENANT_TABLES = (
        "v156_reputation_subjects",
        "v156_reputation_events",
        "v156_reputation_event_relations",
        "v157_reputation_tasks",
        "v156_reputation_merge_logs",
        "v156_reputation_subject_battles",
    )

    def __init__(
        self,
        conn,
        battle_id,
    ):
        self._conn = _v156_a4_base_conn(
            conn
        )

        self._battle_id = (
            _v155_reputation_positive_battle_id(
                battle_id
            )
        )

        self._workspace_id = (
            _v156_a4_workspace_id_for_battle(
                self._conn,
                self._battle_id,
            )
        )

    def __getattr__(
        self,
        name,
    ):
        return getattr(
            self._conn,
            name,
        )

    @staticmethod
    def _is_read_statement(
        sql,
    ):
        return bool(
            re.match(
                r"^(SELECT|WITH)\b",
                str(sql or "").lstrip(),
                flags=re.I,
            )
        )

    def _scope_select(
        self,
        sql,
        params=(),
    ):
        text = str(
            sql or ""
        )

        if not self._is_read_statement(
            text
        ):
            return (
                text,
                params,
            )

        stripped = text.lstrip()

        if re.match(
            r"^WITH\b",
            stripped,
            flags=re.I,
        ):
            raise RuntimeError(
                "A4 operational adapter refuses nested WITH "
                "without explicit review"
            )

        tables = [
            table
            for table in self._TENANT_TABLES
            if re.search(
                r"(?<![A-Za-z0-9_])"
                + re.escape(table)
                + r"(?![A-Za-z0-9_])",
                text,
                flags=re.I,
            )
        ]

        if not tables:
            return (
                text,
                params,
            )

        ctes = []
        scope_params = []

        for table in tables:

            if (
                table
                == "v156_reputation_subjects"
            ):
                ctes.append(
                    """
                    v156_reputation_subjects AS (
                        SELECT *
                        FROM main.v156_reputation_subjects
                        WHERE workspace_id=?
                          AND id IN (
                              SELECT subject_id
                              FROM main.v156_reputation_subject_battles
                              WHERE workspace_id=?
                                AND battle_id=?
                          )
                    )
                    """
                )

                scope_params.extend(
                    [
                        self._workspace_id,
                        self._workspace_id,
                        self._battle_id,
                    ]
                )

            elif (
                table
                == "v156_reputation_event_relations"
            ):
                ctes.append(
                    """
                    v156_reputation_event_relations AS (
                        SELECT *
                        FROM main.v156_reputation_event_relations
                        WHERE workspace_id=?
                          AND subject_id IN (
                              SELECT subject_id
                              FROM main.v156_reputation_subject_battles
                              WHERE workspace_id=?
                                AND battle_id=?
                          )
                    )
                    """
                )

                scope_params.extend(
                    [
                        self._workspace_id,
                        self._workspace_id,
                        self._battle_id,
                    ]
                )

            elif (
                table
                == "v156_reputation_events"
            ):
                ctes.append(
                    """
                    v156_reputation_events AS (
                        SELECT *
                        FROM main.v156_reputation_events
                        WHERE workspace_id=?
                          AND (
                              battle_id=?
                              OR id IN (
                                  SELECT event_id
                                  FROM main.v156_reputation_event_relations
                                  WHERE workspace_id=?
                                    AND subject_id IN (
                                        SELECT subject_id
                                        FROM main.v156_reputation_subject_battles
                                        WHERE workspace_id=?
                                          AND battle_id=?
                                    )
                              )
                          )
                    )
                    """
                )

                scope_params.extend(
                    [
                        self._workspace_id,
                        self._battle_id,
                        self._workspace_id,
                        self._workspace_id,
                        self._battle_id,
                    ]
                )

            elif (
                table
                == "v157_reputation_tasks"
            ):
                ctes.append(
                    """
                    v157_reputation_tasks AS (
                        SELECT *
                        FROM main.v157_reputation_tasks
                        WHERE workspace_id=?
                          AND battle_id=?
                    )
                    """
                )

                scope_params.extend(
                    [
                        self._workspace_id,
                        self._battle_id,
                    ]
                )

            elif (
                table
                == "v156_reputation_subject_battles"
            ):
                ctes.append(
                    """
                    v156_reputation_subject_battles AS (
                        SELECT *
                        FROM main.v156_reputation_subject_battles
                        WHERE workspace_id=?
                          AND battle_id=?
                    )
                    """
                )

                scope_params.extend(
                    [
                        self._workspace_id,
                        self._battle_id,
                    ]
                )

            else:
                ctes.append(
                    table
                    + " AS ("
                    + "SELECT * FROM main."
                    + table
                    + " WHERE workspace_id=?"
                    + ")"
                )

                scope_params.append(
                    self._workspace_id
                )

        scoped_sql = (
            "WITH "
            + ", ".join(
                ctes
            )
            + " "
            + stripped
        )

        if params is None:
            params = ()

        if isinstance(
            params,
            tuple,
        ):
            scoped_params = (
                tuple(
                    scope_params
                )
                + params
            )

        elif isinstance(
            params,
            list,
        ):
            scoped_params = (
                list(
                    scope_params
                )
                + params
            )

        else:
            raise TypeError(
                "A4 operational adapter accepts "
                "tuple/list positional bindings only"
            )

        return (
            scoped_sql,
            scoped_params,
        )

    def execute(
        self,
        sql,
        params=(),
    ):
        sql2, params2 = (
            self._scope_select(
                sql,
                params,
            )
        )

        return self._conn.execute(
            sql2,
            params2,
        )


def get_reputation_event_scoped(
    conn,
    event_id,
    *,
    battle_id,
):
    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    ensure_reputation_tables(
        conn
    )

    row = _v156_a4_base_conn(
        conn
    ).execute(
        """
        SELECT *
        FROM v156_reputation_events
        WHERE id=?
          AND workspace_id=?
        LIMIT 1
        """,
        (
            int(event_id),
            workspace_id,
        ),
    ).fetchone()

    return _v155_reputation_row_dict(
        row
    )


def get_reputation_subject_scoped(
    conn,
    subject_id,
    *,
    battle_id,
):
    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    ensure_reputation_tables(
        conn
    )

    return _v156_a4_base_conn(
        conn
    ).execute(
        """
        SELECT *
        FROM v156_reputation_subjects
        WHERE id=?
          AND workspace_id=?
        LIMIT 1
        """,
        (
            int(subject_id),
            workspace_id,
        ),
    ).fetchone()


def list_reputation_subjects_scoped(
    conn,
    q="",
    limit=100,
    offset=0,
    *,
    battle_id,
):
    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    ensure_reputation_tables(
        conn
    )

    try:
        limit = int(limit)
    except (
        TypeError,
        ValueError,
    ):
        limit = 100

    limit = max(
        1,
        min(
            limit,
            5000,
        ),
    )

    try:
        offset = int(offset)
    except (
        TypeError,
        ValueError,
    ):
        offset = 0

    offset = max(
        0,
        offset,
    )

    q = str(
        q or ""
    ).strip()

    params = [
        workspace_id,
    ]

    where = [
        "workspace_id=?",
    ]

    if q:
        like = (
            "%"
            + q
            + "%"
        )

        where.append(
            """
            (
                   display_name LIKE ?
                OR game_id LIKE ?
                OR alias_names LIKE ?
                OR note LIKE ?
            )
            """
        )

        params.extend(
            [
                like,
                like,
                like,
                like,
            ]
        )

    params.extend(
        [
            limit,
            offset,
        ]
    )

    rows = _v156_a4_base_conn(
        conn
    ).execute(
        """
        SELECT *
        FROM v156_reputation_subjects
        WHERE
        """
        + " AND ".join(
            where
        )
        + """
        ORDER BY id DESC
        LIMIT ?
        OFFSET ?
        """,
        params,
    ).fetchall()

    return _v155_reputation_rows_dict(
        rows
    )


def count_reputation_subjects_scoped(
    conn,
    q="",
    *,
    battle_id,
):
    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    ensure_reputation_tables(
        conn
    )

    q = str(
        q or ""
    ).strip()

    params = [
        workspace_id,
    ]

    where = [
        "workspace_id=?",
    ]

    if q:
        like = (
            "%"
            + q
            + "%"
        )

        where.append(
            """
            (
                   display_name LIKE ?
                OR game_id LIKE ?
                OR alias_names LIKE ?
                OR note LIKE ?
            )
            """
        )

        params.extend(
            [
                like,
                like,
                like,
                like,
            ]
        )

    row = _v156_a4_base_conn(
        conn
    ).execute(
        """
        SELECT COUNT(*)
        FROM v156_reputation_subjects
        WHERE
        """
        + " AND ".join(
            where
        ),
        params,
    ).fetchone()

    return int(
        row[0]
        if row
        else 0
    )



def list_reputation_events_scoped(
    conn,
    q="",
    limit=100,
    *,
    battle_id,
):
    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    ensure_reputation_tables(
        conn
    )

    try:
        limit = int(limit)
    except (
        TypeError,
        ValueError,
    ):
        limit = 100

    limit = max(
        1,
        min(
            limit,
            5000,
        ),
    )

    q = str(
        q or ""
    ).strip()

    columns = {
        str(row[1])
        for row in _v156_a4_base_conn(
            conn
        ).execute(
            """
            PRAGMA table_info(
                v156_reputation_events
            )
            """
        ).fetchall()
    }

    search_columns = [
        name
        for name in (
            "title",
            "event_type",
            "summary",
            "evidence_note",
            "note",
        )
        if name in columns
    ]

    where = [
        "workspace_id=?",
    ]

    params = [
        workspace_id,
    ]

    if q and search_columns:
        where.append(
            "("
            + " OR ".join(
                "IFNULL("
                + name
                + ", '') LIKE ?"
                for name
                in search_columns
            )
            + ")"
        )

        params.extend(
            [
                "%"
                + q
                + "%"
            ]
            * len(
                search_columns
            )
        )

    if "updated_at" in columns:
        order_sql = (
            "updated_at DESC, id DESC"
        )

    elif "created_at" in columns:
        order_sql = (
            "created_at DESC, id DESC"
        )

    elif "event_time" in columns:
        order_sql = (
            "event_time DESC, id DESC"
        )

    else:
        order_sql = (
            "id DESC"
        )

    params.append(
        limit
    )

    rows = _v156_a4_base_conn(
        conn
    ).execute(
        """
        SELECT *
        FROM v156_reputation_events
        WHERE
        """
        + " AND ".join(
            where
        )
        + " ORDER BY "
        + order_sql
        + " LIMIT ?",
        params,
    ).fetchall()

    return _v155_reputation_rows_dict(
        rows
    )


def list_reputation_event_relations_scoped(
    conn,
    event_id,
    *,
    battle_id,
):
    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    rows = _v156_a4_base_conn(
        conn
    ).execute(
        """
        SELECT
            r.*,
            s.display_name,
            s.game_id,
            s.alias_names,
            s.trust_level,
            s.risk_level,
            s.status AS subject_status
        FROM v156_reputation_event_relations AS r
        LEFT JOIN v156_reputation_subjects AS s
          ON s.id = r.subject_id
         AND s.workspace_id = r.workspace_id
        WHERE r.event_id=?
          AND r.workspace_id=?
        ORDER BY r.id DESC
        """,
        (
            int(event_id),
            workspace_id,
        ),
    ).fetchall()

    return _v155_reputation_rows_dict(
        rows
    )


def build_reputation_home_report_scoped(
    conn,
    *,
    battle_id,
):
    scoped = (
        make_reputation_workspace_scoped_connection(
            conn,
            battle_id,
        )
    )

    return build_reputation_home_report(
        scoped
    )


def search_reputation_scoped(
    conn,
    q,
    *,
    battle_id,
):
    scoped = (
        make_reputation_workspace_scoped_connection(
            conn,
            battle_id,
        )
    )

    return search_reputation(
        scoped,
        q,
    )


def list_reputation_events_by_subject_scoped(
    conn,
    subject_id,
    *,
    battle_id,
):
    scoped = (
        make_reputation_workspace_scoped_connection(
            conn,
            battle_id,
        )
    )

    return list_reputation_events_by_subject(
        scoped,
        subject_id,
    )


def list_reputation_merge_logs_scoped(
    conn,
    limit=100,
    *,
    battle_id,
):
    scoped = (
        make_reputation_workspace_scoped_connection(
            conn,
            battle_id,
        )
    )

    return list_reputation_merge_logs(
        scoped,
        limit=limit,
    )


def build_reputation_duplicate_report_scoped(
    conn,
    *,
    battle_id,
):
    scoped = (
        make_reputation_workspace_scoped_connection(
            conn,
            battle_id,
        )
    )

    return build_reputation_duplicate_report(
        scoped
    )


def create_reputation_subject_scoped(
    conn,
    data,
    *,
    battle_id,
):
    battle_id = (
        _v155_reputation_positive_battle_id(
            battle_id
        )
    )

    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    ensure_reputation_tables(
        conn
    )

    base = _v156_a4_base_conn(
        conn
    )

    game_id = str(
        data.get(
            "game_id",
            "",
        )
        or ""
    ).strip()

    if game_id:
        existing = base.execute(
            """
            SELECT id
            FROM v156_reputation_subjects
            WHERE workspace_id=?
              AND TRIM(game_id)=?
            LIMIT 1
            """,
            (
                workspace_id,
                game_id,
            ),
        ).fetchone()

        if existing is not None:
            subject_id = int(
                existing[0]
            )

            _v156_a4_link_subject_battle(
                base,
                workspace_id=workspace_id,
                subject_id=subject_id,
                battle_id=battle_id,
                source_type="game_id_reuse",
            )

            base.commit()

            return subject_id

    cursor = base.execute(
        """
        INSERT INTO v156_reputation_subjects (
            workspace_id,
            battle_id,
            subject_type,
            display_name,
            game_id,
            alias_names,
            trust_level,
            risk_level,
            status,
            source_type,
            note,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            datetime('now','localtime')
        )
        """,
        (
            workspace_id,
            battle_id,
            (
                data.get(
                    "subject_type"
                )
                or "player"
            ).strip(),
            (
                data.get(
                    "display_name"
                )
                or ""
            ).strip(),
            game_id,
            (
                data.get(
                    "alias_names"
                )
                or ""
            ).strip(),
            (
                data.get(
                    "trust_level"
                )
                or "unknown"
            ).strip(),
            (
                data.get(
                    "risk_level"
                )
                or "normal"
            ).strip(),
            (
                data.get(
                    "status"
                )
                or "active"
            ).strip(),
            (
                data.get(
                    "source_type"
                )
                or data.get(
                    "source"
                )
                or "manual"
            ).strip(),
            (
                data.get(
                    "note"
                )
                or ""
            ).strip(),
        ),
    )

    subject_id = int(
        cursor.lastrowid
    )

    _v156_a4_link_subject_battle(
        base,
        workspace_id=workspace_id,
        subject_id=subject_id,
        battle_id=battle_id,
        source_type="subject_create",
    )

    base.commit()

    return subject_id


def update_reputation_subject_scoped(
    conn,
    subject_id,
    data,
    *,
    battle_id,
):
    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    base = _v156_a4_base_conn(
        conn
    )

    row = base.execute(
        """
        SELECT *
        FROM v156_reputation_subjects
        WHERE id=?
          AND workspace_id=?
        LIMIT 1
        """,
        (
            int(subject_id),
            workspace_id,
        ),
    ).fetchone()

    if row is None:
        return False

    current = dict(row)

    game_id = str(
        data.get(
            "game_id",
            current.get(
                "game_id",
                "",
            ),
        )
        or ""
    ).strip()

    if game_id:
        duplicate = base.execute(
            """
            SELECT id
            FROM v156_reputation_subjects
            WHERE workspace_id=?
              AND TRIM(game_id)=?
              AND id<>?
            LIMIT 1
            """,
            (
                workspace_id,
                game_id,
                int(subject_id),
            ),
        ).fetchone()

        if duplicate is not None:
            return False

    cursor = base.execute(
        """
        UPDATE v156_reputation_subjects
        SET
            subject_type=?,
            display_name=?,
            game_id=?,
            alias_names=?,
            trust_level=?,
            risk_level=?,
            status=?,
            source_type=?,
            note=?,
            updated_at=datetime(
                'now',
                'localtime'
            )
        WHERE id=?
          AND workspace_id=?
        """,
        (
            (
                data.get(
                    "subject_type"
                )
                or current.get(
                    "subject_type"
                )
                or "player"
            ).strip(),
            (
                data.get(
                    "display_name"
                )
                if data.get(
                    "display_name"
                ) is not None
                else current.get(
                    "display_name"
                )
            )
            or "",
            game_id,
            (
                data.get(
                    "alias_names"
                )
                if data.get(
                    "alias_names"
                ) is not None
                else current.get(
                    "alias_names"
                )
            )
            or "",
            (
                data.get(
                    "trust_level"
                )
                or current.get(
                    "trust_level"
                )
                or "unknown"
            ).strip(),
            (
                data.get(
                    "risk_level"
                )
                or current.get(
                    "risk_level"
                )
                or "normal"
            ).strip(),
            (
                data.get(
                    "status"
                )
                or current.get(
                    "status"
                )
                or "active"
            ).strip(),
            (
                data.get(
                    "source_type"
                )
                or data.get(
                    "source"
                )
                or current.get(
                    "source_type"
                )
                or "manual"
            ).strip(),
            (
                data.get(
                    "note"
                )
                if data.get(
                    "note"
                ) is not None
                else current.get(
                    "note"
                )
            )
            or "",
            int(subject_id),
            workspace_id,
        ),
    )

    base.commit()

    return (
        cursor.rowcount
        == 1
    )


def create_reputation_event_scoped(
    conn,
    data,
    *,
    battle_id,
):
    battle_id = (
        _v155_reputation_positive_battle_id(
            battle_id
        )
    )

    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    ensure_reputation_tables(
        conn
    )

    base = _v156_a4_base_conn(
        conn
    )

    cursor = base.execute(
        """
        INSERT INTO v156_reputation_events (
            workspace_id,
            battle_id,
            title,
            event_type,
            impact_level,
            status,
            event_time,
            summary,
            evidence_note,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?,
            datetime('now','localtime')
        )
        """,
        (
            workspace_id,
            battle_id,
            (
                data.get(
                    "title"
                )
                or ""
            ).strip(),
            (
                data.get(
                    "event_type"
                )
                or "general"
            ).strip(),
            (
                data.get(
                    "impact_level"
                )
                or "normal"
            ).strip(),
            (
                data.get(
                    "status"
                )
                or "recorded"
            ).strip(),
            (
                data.get(
                    "event_time"
                )
                or ""
            ).strip(),
            (
                data.get(
                    "summary"
                )
                or ""
            ).strip(),
            (
                data.get(
                    "evidence_note"
                )
                or ""
            ).strip(),
        ),
    )

    base.commit()

    return int(
        cursor.lastrowid
    )


def update_reputation_event_scoped(
    conn,
    event_id,
    data,
    *,
    battle_id,
):
    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    base = _v156_a4_base_conn(
        conn
    )

    row = base.execute(
        """
        SELECT *
        FROM v156_reputation_events
        WHERE id=?
          AND workspace_id=?
        LIMIT 1
        """,
        (
            int(event_id),
            workspace_id,
        ),
    ).fetchone()

    if row is None:
        return False

    current = dict(row)

    fields = (
        "title",
        "event_type",
        "impact_level",
        "status",
        "event_time",
        "summary",
        "evidence_note",
    )

    values = [
        data.get(
            field,
            current.get(
                field,
                "",
            ),
        )
        for field
        in fields
    ]

    cursor = base.execute(
        """
        UPDATE v156_reputation_events
        SET
            title=?,
            event_type=?,
            impact_level=?,
            status=?,
            event_time=?,
            summary=?,
            evidence_note=?,
            updated_at=datetime(
                'now',
                'localtime'
            )
        WHERE id=?
          AND workspace_id=?
        """,
        tuple(values)
        + (
            int(event_id),
            workspace_id,
        ),
    )

    base.commit()

    return (
        cursor.rowcount
        == 1
    )


def add_reputation_event_relation_scoped(
    conn,
    event_id,
    subject_id,
    relation_role="",
    note="",
    *,
    battle_id,
):
    battle_id = (
        _v155_reputation_positive_battle_id(
            battle_id
        )
    )

    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    base = _v156_a4_base_conn(
        conn
    )

    event = base.execute(
        """
        SELECT id
        FROM v156_reputation_events
        WHERE id=?
          AND workspace_id=?
        LIMIT 1
        """,
        (
            int(event_id),
            workspace_id,
        ),
    ).fetchone()

    subject = base.execute(
        """
        SELECT id
        FROM v156_reputation_subjects
        WHERE id=?
          AND workspace_id=?
        LIMIT 1
        """,
        (
            int(subject_id),
            workspace_id,
        ),
    ).fetchone()

    if (
        event is None
        or subject is None
    ):
        raise ValueError(
            "event and subject must belong "
            "to the same workspace"
        )

    existing = base.execute(
        """
        SELECT id
        FROM v156_reputation_event_relations
        WHERE workspace_id=?
          AND event_id=?
          AND subject_id=?
        LIMIT 1
        """,
        (
            workspace_id,
            int(event_id),
            int(subject_id),
        ),
    ).fetchone()

    if existing is not None:
        relation_id = int(
            existing[0]
        )

    else:
        cursor = base.execute(
            """
            INSERT INTO
            v156_reputation_event_relations (
                workspace_id,
                battle_id,
                event_id,
                subject_id,
                relation_role,
                note
            )
            VALUES (
                ?, ?, ?, ?, ?, ?
            )
            """,
            (
                workspace_id,
                battle_id,
                int(event_id),
                int(subject_id),
                str(
                    relation_role
                    or ""
                ).strip(),
                str(
                    note
                    or ""
                ).strip(),
            ),
        )

        relation_id = int(
            cursor.lastrowid
        )

    _v156_a4_link_subject_battle(
        base,
        workspace_id=workspace_id,
        subject_id=int(
            subject_id
        ),
        battle_id=battle_id,
        source_type="event_relation",
    )

    base.commit()

    return relation_id


def delete_reputation_event_relation_scoped(
    conn,
    event_id,
    relation_id,
    *,
    battle_id,
):
    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    cursor = _v156_a4_base_conn(
        conn
    ).execute(
        """
        DELETE FROM
            v156_reputation_event_relations
        WHERE id=?
          AND event_id=?
          AND workspace_id=?
        """,
        (
            int(relation_id),
            int(event_id),
            workspace_id,
        ),
    )

    _v156_a4_base_conn(
        conn
    ).commit()

    return (
        cursor.rowcount
        == 1
    )


def update_reputation_event_status_quick_scoped(
    conn,
    event_id,
    *,
    status,
    note="",
    battle_id,
):
    row = get_reputation_event_scoped(
        conn,
        event_id,
        battle_id=battle_id,
    )

    if not row:
        return {
            "ok": False,
            "not_found": True,
            "message": "事件不存在。",
        }

    return update_reputation_event_status_quick(
        _v156_a4_base_conn(
            conn
        ),
        event_id=event_id,
        status=status,
        note=note,
    )


def delete_reputation_event_safely_scoped(
    conn,
    event_id,
    *,
    battle_id,
):
    row = get_reputation_event_scoped(
        conn,
        event_id,
        battle_id=battle_id,
    )

    if not row:
        return {
            "ok": False,
            "not_found": True,
            "message": "事件不存在。",
        }

    return delete_reputation_event_safely(
        _v156_a4_base_conn(
            conn
        ),
        event_id,
    )


def delete_reputation_subject_safely_scoped(
    conn,
    subject_id,
    *,
    battle_id,
):
    row = get_reputation_subject_scoped(
        conn,
        subject_id,
        battle_id=battle_id,
    )

    if not row:
        return {
            "ok": False,
            "not_found": True,
            "message": "主体不存在。",
        }

    base = _v156_a4_base_conn(
        conn
    )

    result = delete_reputation_subject_safely(
        base,
        subject_id,
    )

    if (
        not isinstance(
            result,
            dict,
        )
        or result.get(
            "ok",
            True,
        )
    ):
        base.execute(
            """
            DELETE FROM
                v156_reputation_subject_battles
            WHERE subject_id=?
              AND workspace_id=?
            """,
            (
                int(subject_id),
                int(
                    row[
                        "workspace_id"
                    ]
                ),
            ),
        )

        base.commit()

    return result


def merge_reputation_subjects_scoped(
    conn,
    keep_id,
    merge_id,
    *,
    battle_id,
):
    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    base = _v156_a4_base_conn(
        conn
    )

    owned = base.execute(
        """
        SELECT id
        FROM v156_reputation_subjects
        WHERE workspace_id=?
          AND id IN (?, ?)
        ORDER BY id
        """,
        (
            workspace_id,
            int(keep_id),
            int(merge_id),
        ),
    ).fetchall()

    if len(owned) != 2:
        return {
            "ok": False,
            "message":
                "主体不存在或不属于当前工作区。",
        }

    result = merge_reputation_subjects(
        base,
        keep_id=int(
            keep_id
        ),
        merge_id=int(
            merge_id
        ),
        battle_id=int(
            battle_id
        ),
    )

    failed = (
        isinstance(
            result,
            dict,
        )
        and result.get(
            "ok"
        )
        is False
    )

    if failed:
        return result

    base.execute(
        """
        INSERT OR IGNORE INTO
        v156_reputation_subject_battles (
            workspace_id,
            subject_id,
            battle_id,
            first_seen_at,
            last_seen_at,
            source_type,
            created_at,
            updated_at
        )
        SELECT
            workspace_id,
            ?,
            battle_id,
            first_seen_at,
            last_seen_at,
            'merge_preserved',
            created_at,
            datetime('now','localtime')
        FROM v156_reputation_subject_battles
        WHERE workspace_id=?
          AND subject_id=?
        """,
        (
            int(keep_id),
            workspace_id,
            int(merge_id),
        ),
    )

    base.execute(
        """
        DELETE FROM
            v156_reputation_subject_battles
        WHERE workspace_id=?
          AND subject_id=?
        """,
        (
            workspace_id,
            int(merge_id),
        ),
    )

    base.execute(
        """
        UPDATE v156_reputation_merge_logs
        SET workspace_id=?
        WHERE workspace_id IS NULL
          AND keep_subject_id=?
          AND merge_subject_id=?
        """,
        (
            workspace_id,
            int(keep_id),
            int(merge_id),
        ),
    )

    base.commit()

    return result


def get_reputation_task_scoped(
    conn,
    task_id,
    *,
    battle_id,
):
    battle_id = (
        _v155_reputation_positive_battle_id(
            battle_id
        )
    )

    workspace_id = (
        _v156_a4_workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    ensure_reputation_tables(
        conn
    )

    return _v156_a4_base_conn(
        conn
    ).execute(
        """
        SELECT *
        FROM v157_reputation_tasks
        WHERE id=?
          AND workspace_id=?
          AND battle_id=?
        """,
        (
            int(task_id),
            workspace_id,
            battle_id,
        ),
    ).fetchone()


def update_reputation_task_scoped(
    conn,
    task_id,
    data,
    *,
    battle_id,
):
    row = get_reputation_task_scoped(
        conn,
        task_id,
        battle_id=battle_id,
    )

    if not row:
        return {
            "ok": False,
            "not_found": True,
            "message": "处置任务不存在。",
        }

    return update_reputation_task(
        _v156_a4_base_conn(
            conn
        ),
        task_id,
        data,
    )
