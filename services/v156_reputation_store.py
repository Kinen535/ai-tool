from __future__ import annotations

import sqlite3
from typing import Any


def ensure_reputation_tables(conn: sqlite3.Connection) -> None:
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


def merge_reputation_subjects(
    conn: sqlite3.Connection,
    keep_id: int,
    merge_id: int,
) -> dict[str, Any]:
    ensure_reputation_tables(conn)
    # V15.6-A12 merge audit init
    ensure_reputation_merge_log_table(conn)

    if not keep_id or not merge_id:
        return {"ok": False, "message": "缺少主体 ID。"}

    if keep_id == merge_id:
        return {"ok": False, "message": "保留主体和被合并主体不能相同。"}

    keep = conn.execute(
        "SELECT * FROM v156_reputation_subjects WHERE id=?",
        (keep_id,),
    ).fetchone()

    merge = conn.execute(
        "SELECT * FROM v156_reputation_subjects WHERE id=?",
        (merge_id,),
    ).fetchone()

    if not keep or not merge:
        return {"ok": False, "message": "主体不存在，无法合并。"}

    # V15.6-A12 merge audit relation stats
    merge_relation_total = int(
        conn.execute(
            "SELECT COUNT(*) FROM v156_reputation_event_relations WHERE subject_id=?",
            (merge_id,),
        ).fetchone()[0] or 0
    )

    duplicate_relation_total = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM v156_reputation_event_relations mr
            INNER JOIN v156_reputation_event_relations kr
                ON kr.event_id = mr.event_id
               AND kr.subject_id = ?
            WHERE mr.subject_id = ?
            """,
            (keep_id, merge_id),
        ).fetchone()[0] or 0
    )

    moved_relation_total = max(0, merge_relation_total - duplicate_relation_total)

    keep_name = (keep["display_name"] or "").strip()
    merge_name = (merge["display_name"] or "").strip()

    alias_items: list[str] = []

    for item in _v156_split_aliases(keep["alias_names"]):
        if item not in alias_items:
            alias_items.append(item)

    if merge_name and merge_name != keep_name and merge_name not in alias_items:
        alias_items.append(merge_name)

    for item in _v156_split_aliases(merge["alias_names"]):
        if item and item != keep_name and item not in alias_items:
            alias_items.append(item)

    merged_alias_names = ",".join(alias_items)

    merged_game_id = (keep["game_id"] or "").strip() or (merge["game_id"] or "").strip()

    merged_trust_level = _v156_pick_worse_level(
        keep["trust_level"],
        merge["trust_level"],
        ["unknown", "trusted", "risky", "black"],
    )

    merged_risk_level = _v156_pick_worse_level(
        keep["risk_level"],
        merge["risk_level"],
        ["normal", "warning", "danger", "black"],
    )

    keep_note = (keep["note"] or "").strip()
    merge_note = (merge["note"] or "").strip()

    merge_info = f"已合并主体 #{merge_id}"
    if merge_name:
        merge_info += f"：{merge_name}"
    if merge["game_id"]:
        merge_info += f"｜{merge['game_id']}"

    note_parts = [x for x in [keep_note, merge_note, merge_info] if x]
    merged_note = "\n\n".join(note_parts)

    # 先迁移不重复的事件关联
    conn.execute(
        """
        UPDATE v156_reputation_event_relations
        SET subject_id=?
        WHERE subject_id=?
          AND event_id NOT IN (
              SELECT event_id
              FROM v156_reputation_event_relations
              WHERE subject_id=?
          )
        """,
        (keep_id, merge_id, keep_id),
    )

    # 删除迁移后仍然剩下的重复关联，避免同一事件同一主体重复绑定
    conn.execute(
        """
        DELETE FROM v156_reputation_event_relations
        WHERE subject_id=?
        """,
        (merge_id,),
    )

    conn.execute(
        """
        UPDATE v156_reputation_subjects
        SET
            game_id=?,
            alias_names=?,
            trust_level=?,
            risk_level=?,
            note=?,
            updated_at=datetime('now','localtime')
        WHERE id=?
        """,
        (
            merged_game_id,
            merged_alias_names,
            merged_trust_level,
            merged_risk_level,
            merged_note,
            keep_id,
        ),
    )

    conn.execute(
        """
        DELETE FROM v156_reputation_subjects
        WHERE id=?
        """,
        (merge_id,),
    )

    # V15.6-A12 write merge audit log
    import json

    conn.execute(
        """
        INSERT INTO v156_reputation_merge_logs (
            keep_subject_id,
            keep_display_name,
            keep_game_id,
            merge_subject_id,
            merge_display_name,
            merge_game_id,
            moved_relations_count,
            removed_duplicate_relations_count,
            keep_snapshot,
            merge_snapshot,
            result_message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
        """,
        (
            keep_id,
            keep_name,
            merged_game_id,
            merge_id,
            merge_name,
            (merge["game_id"] or "").strip(),
            moved_relation_total,
            duplicate_relation_total,
            json.dumps(dict(keep), ensure_ascii=False),
            json.dumps(dict(merge), ensure_ascii=False),
            f"已合并主体 #{merge_id} 到 #{keep_id}",
        ),
    )

    conn.commit()

    return {
        "ok": True,
        "message": f"已合并主体 #{merge_id} 到 #{keep_id}。",
        "keep_id": keep_id,
        "merge_id": merge_id,
    }


# =========================
# V15.6-A12 reputation merge audit logs
# =========================

def ensure_reputation_merge_log_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v156_reputation_merge_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keep_subject_id INTEGER,
            keep_display_name TEXT,
            keep_game_id TEXT,
            merge_subject_id INTEGER,
            merge_display_name TEXT,
            merge_game_id TEXT,
            moved_relations_count INTEGER DEFAULT 0,
            removed_duplicate_relations_count INTEGER DEFAULT 0,
            keep_snapshot TEXT,
            merge_snapshot TEXT,
            result_message TEXT,
            created_at TEXT
        )
        """
    )
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


def get_reputation_event_scoped(conn, event_id, *, battle_id):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    row = conn.execute(
        """
        SELECT *
        FROM v156_reputation_events
        WHERE id = ?
          AND battle_id = ?
        LIMIT 1
        """,
        (
            event_id,
            battle_id,
        ),
    ).fetchone()

    return _v155_reputation_row_dict(row)


def update_reputation_event_scoped(
    conn,
    event_id,
    data,
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    row = conn.execute(
        """
        SELECT *
        FROM v156_reputation_events
        WHERE id = ?
          AND battle_id = ?
        LIMIT 1
        """,
        (
            event_id,
            battle_id,
        ),
    ).fetchone()

    if row is None:
        return False

    current = _v155_reputation_row_dict(row)

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

    cur = conn.execute(
        """
        UPDATE v156_reputation_events
        SET title = ?,
            event_type = ?,
            impact_level = ?,
            status = ?,
            event_time = ?,
            summary = ?,
            evidence_note = ?,
            updated_at = datetime('now','localtime')
        WHERE id = ?
          AND battle_id = ?
        """,
        tuple(values)
        + (
            event_id,
            battle_id,
        ),
    )

    conn.commit()

    return cur.rowcount == 1


def list_reputation_event_relations_scoped(
    conn,
    event_id,
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    rows = conn.execute(
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
         AND s.battle_id = r.battle_id
        WHERE r.event_id = ?
          AND r.battle_id = ?
        ORDER BY r.id DESC
        """,
        (
            event_id,
            battle_id,
        ),
    ).fetchall()

    return _v155_reputation_rows_dict(rows)


def list_reputation_subjects_scoped(
    conn,
    q="",
    limit=100,
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    try:
        limit = int(limit)
    except (TypeError, ValueError):
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

    if q:
        like = "%" + q + "%"

        rows = conn.execute(
            """
            SELECT *
            FROM v156_reputation_subjects
            WHERE battle_id = ?
              AND (
                    display_name LIKE ?
                 OR game_id LIKE ?
                 OR alias_names LIKE ?
                 OR note LIKE ?
              )
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                battle_id,
                like,
                like,
                like,
                like,
                limit,
            ),
        ).fetchall()

    else:
        rows = conn.execute(
            """
            SELECT *
            FROM v156_reputation_subjects
            WHERE battle_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                battle_id,
                limit,
            ),
        ).fetchall()

    return _v155_reputation_rows_dict(rows)


def create_reputation_subject_scoped(
    conn,
    data,
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    cur = conn.execute(
        """
        INSERT INTO v156_reputation_subjects (
            battle_id,
            subject_type,
            display_name,
            game_id,
            alias_names,
            trust_level,
            risk_level,
            status,
            source_type,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            battle_id,
            data.get("subject_type", "player"),
            data.get("display_name", ""),
            data.get("game_id", ""),
            data.get("alias_names", ""),
            data.get("trust_level", "unknown"),
            data.get("risk_level", "normal"),
            data.get("status", "active"),
            data.get("source_type", "manual"),
            data.get("note", ""),
        ),
    )

    conn.commit()

    return cur.lastrowid


def create_reputation_event_scoped(
    conn,
    data,
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    cur = conn.execute(
        """
        INSERT INTO v156_reputation_events (
            battle_id,
            title,
            event_type,
            impact_level,
            status,
            event_time,
            summary,
            evidence_note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            battle_id,
            data.get("title", ""),
            data.get("event_type", "general"),
            data.get("impact_level", "normal"),
            data.get("status", "recorded"),
            data.get("event_time", ""),
            data.get("summary", ""),
            data.get("evidence_note", ""),
        ),
    )

    conn.commit()

    return cur.lastrowid


def add_reputation_event_relation_scoped(
    conn,
    event_id,
    subject_id,
    relation_role="",
    note="",
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    event = conn.execute(
        """
        SELECT id
        FROM v156_reputation_events
        WHERE id = ?
          AND battle_id = ?
        LIMIT 1
        """,
        (
            event_id,
            battle_id,
        ),
    ).fetchone()

    subject = conn.execute(
        """
        SELECT id
        FROM v156_reputation_subjects
        WHERE id = ?
          AND battle_id = ?
        LIMIT 1
        """,
        (
            subject_id,
            battle_id,
        ),
    ).fetchone()

    if (
        event is None
        or subject is None
    ):
        return None

    existing = conn.execute(
        """
        SELECT id
        FROM v156_reputation_event_relations
        WHERE event_id = ?
          AND subject_id = ?
          AND battle_id = ?
        LIMIT 1
        """,
        (
            event_id,
            subject_id,
            battle_id,
        ),
    ).fetchone()

    if existing is not None:

        try:
            relation_id = int(
                existing["id"]
            )
        except Exception:
            relation_id = int(
                existing[0]
            )

        conn.execute(
            """
            UPDATE v156_reputation_event_relations
            SET relation_role = ?,
                note = ?
            WHERE id = ?
              AND event_id = ?
              AND subject_id = ?
              AND battle_id = ?
            """,
            (
                relation_role,
                note,
                relation_id,
                event_id,
                subject_id,
                battle_id,
            ),
        )

        conn.commit()

        return relation_id

    cur = conn.execute(
        """
        INSERT INTO v156_reputation_event_relations (
            battle_id,
            event_id,
            subject_id,
            relation_role,
            note
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            battle_id,
            event_id,
            subject_id,
            relation_role,
            note,
        ),
    )

    conn.commit()

    return cur.lastrowid


def delete_reputation_event_relation_scoped(
    conn,
    relation_id,
    *,
    event_id,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    cur = conn.execute(
        """
        DELETE FROM v156_reputation_event_relations
        WHERE id = ?
          AND event_id = ?
          AND battle_id = ?
        """,
        (
            relation_id,
            event_id,
            battle_id,
        ),
    )

    conn.commit()

    return cur.rowcount == 1


def update_reputation_event_status_quick_scoped(
    conn,
    event_id,
    status,
    note="",
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    current = conn.execute(
        """
        SELECT id
        FROM v156_reputation_events
        WHERE id = ?
          AND battle_id = ?
        LIMIT 1
        """,
        (
            event_id,
            battle_id,
        ),
    ).fetchone()

    if current is None:
        return {
            "ok": False,
            "message": "事件不存在或不属于当前战场",
        }

    status = str(
        status or ""
    ).strip()

    note = str(
        note or ""
    ).strip()

    if not status:
        return {
            "ok": False,
            "message": "状态不能为空",
        }

    cur = conn.execute(
        """
        UPDATE v156_reputation_events
        SET status = ?,
            evidence_note = CASE
                WHEN ? = '' THEN evidence_note
                WHEN COALESCE(evidence_note, '') = '' THEN ?
                ELSE evidence_note || char(10) || ?
            END,
            updated_at = datetime('now','localtime')
        WHERE id = ?
          AND battle_id = ?
        """,
        (
            status,
            note,
            note,
            note,
            event_id,
            battle_id,
        ),
    )

    conn.commit()

    return {
        "ok": (
            cur.rowcount
            == 1
        ),
        "message": (
            "状态已更新"
            if cur.rowcount == 1
            else "状态更新失败"
        ),
    }


def delete_reputation_event_safely_scoped(
    conn,
    event_id,
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    row = conn.execute(
        """
        SELECT
            id,
            title,
            event_type,
            impact_level,
            status
        FROM v156_reputation_events
        WHERE id = ?
          AND battle_id = ?
        LIMIT 1
        """,
        (
            event_id,
            battle_id,
        ),
    ).fetchone()

    if row is None:
        return {
            "ok": False,
            "blocked": False,
            "event_id": event_id,
        }

    current = _v155_reputation_row_dict(
        row
    )

    relation_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM v156_reputation_event_relations
            WHERE event_id = ?
              AND battle_id = ?
            """,
            (
                event_id,
                battle_id,
            ),
        ).fetchone()[0]
        or 0
    )

    if relation_count > 0:
        return {
            "ok": False,
            "blocked": True,
            "event_id": event_id,
            "title": current.get(
                "title",
                "",
            ),
            "relation_count":
                relation_count,
        }

    cur = conn.execute(
        """
        DELETE FROM v156_reputation_events
        WHERE id = ?
          AND battle_id = ?
        """,
        (
            event_id,
            battle_id,
        ),
    )

    conn.commit()

    return {
        "ok": (
            cur.rowcount
            == 1
        ),
        "blocked": False,
        "event_id": event_id,
        "title": current.get(
            "title",
            "",
        ),
        "relation_count": 0,
    }


def delete_reputation_subject_safely_scoped(
    conn,
    subject_id,
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    row = conn.execute(
        """
        SELECT
            id,
            display_name,
            game_id
        FROM v156_reputation_subjects
        WHERE id = ?
          AND battle_id = ?
        LIMIT 1
        """,
        (
            subject_id,
            battle_id,
        ),
    ).fetchone()

    if row is None:
        return {
            "ok": False,
            "blocked": False,
            "subject_id": subject_id,
        }

    current = _v155_reputation_row_dict(
        row
    )

    relation_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM v156_reputation_event_relations
            WHERE subject_id = ?
              AND battle_id = ?
            """,
            (
                subject_id,
                battle_id,
            ),
        ).fetchone()[0]
        or 0
    )

    first_event = conn.execute(
        """
        SELECT event_id
        FROM v156_reputation_event_relations
        WHERE subject_id = ?
          AND battle_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            subject_id,
            battle_id,
        ),
    ).fetchone()

    first_event_id = 0

    if first_event is not None:
        try:
            first_event_id = int(
                first_event["event_id"]
            )
        except Exception:
            first_event_id = int(
                first_event[0]
            )

    if relation_count > 0:
        return {
            "ok": False,
            "blocked": True,
            "subject_id": subject_id,
            "display_name": current.get(
                "display_name",
                "",
            ),
            "relation_count":
                relation_count,
            "first_event_id":
                first_event_id,
        }

    cur = conn.execute(
        """
        DELETE FROM v156_reputation_subjects
        WHERE id = ?
          AND battle_id = ?
        """,
        (
            subject_id,
            battle_id,
        ),
    )

    conn.commit()

    return {
        "ok": (
            cur.rowcount
            == 1
        ),
        "blocked": False,
        "subject_id": subject_id,
        "display_name": current.get(
            "display_name",
            "",
        ),
        "relation_count": 0,
        "first_event_id": 0,
    }

# ============================================================
# V15.5-A5-P0-S08 battle-scoped reputation helpers
# ============================================================

def get_reputation_subject_scoped(conn: sqlite3.Connection, subject_id: int, *, battle_id):
    battle_id = _v155_reputation_positive_battle_id(battle_id)
    ensure_reputation_tables(conn)
    return conn.execute('\n        SELECT *\n        FROM v156_reputation_subjects\n        WHERE id=?\n          AND battle_id = ?\n        ', (subject_id, battle_id)).fetchone()

def update_reputation_subject_scoped(conn: sqlite3.Connection, subject_id: int, data: dict[str, Any], *, battle_id) -> bool:
    battle_id = _v155_reputation_positive_battle_id(battle_id)
    ensure_reputation_tables(conn)
    display_name = (data.get('display_name') or '').strip()
    game_id = (data.get('game_id') or '').strip()
    if not display_name and (not game_id):
        return False
    conn.execute("\n        UPDATE v156_reputation_subjects\n        SET\n            subject_type=?,\n            display_name=?,\n            game_id=?,\n            alias_names=?,\n            trust_level=?,\n            risk_level=?,\n            status=?,\n            source_type=?,\n            note=?,\n            updated_at=datetime('now','localtime')\n        WHERE id=?\n          AND battle_id = ?\n        ", ((data.get('subject_type') or 'player').strip(), display_name, game_id, (data.get('alias_names') or '').strip(), (data.get('trust_level') or 'unknown').strip(), (data.get('risk_level') or 'normal').strip(), (data.get('status') or 'active').strip(), (data.get('source_type') or 'manual').strip(), (data.get('note') or '').strip(), subject_id, battle_id))
    conn.commit()
    return True

def get_reputation_task_scoped(conn: sqlite3.Connection, task_id: int, *, battle_id):
    battle_id = _v155_reputation_positive_battle_id(battle_id)
    ensure_reputation_tables(conn)
    return conn.execute('\n        SELECT *\n        FROM v157_reputation_tasks\n        WHERE id=?\n          AND battle_id = ?\n        ', (task_id, battle_id)).fetchone()

def update_reputation_task_scoped(conn: sqlite3.Connection, task_id: int, data: dict[str, Any], *, battle_id) -> dict[str, Any]:
    battle_id = _v155_reputation_positive_battle_id(battle_id)
    ensure_reputation_tables(conn)
    row = get_reputation_task_scoped(conn, task_id, battle_id=battle_id)
    if not row:
        return {'ok': False, 'not_found': True, 'message': '处置任务不存在。'}
    priority = (data.get('priority') or row['priority'] or 'P3').strip().upper()
    status = (data.get('status') or row['status'] or 'pending').strip().lower()
    owner = data.get('owner') if data.get('owner') is not None else row['owner']
    result_note = data.get('result_note') if data.get('result_note') is not None else row['result_note']
    owner = (owner or '').strip()
    result_note = (result_note or '').strip()
    if priority not in _REPUTATION_TASK_PRIORITIES:
        return {'ok': False, 'message': '任务优先级无效。'}
    if status not in _REPUTATION_TASK_STATUSES:
        return {'ok': False, 'message': '任务状态无效。'}
    if len(owner) > 100:
        return {'ok': False, 'message': '负责人名称不能超过100个字符。'}
    if len(result_note) > 2000:
        return {'ok': False, 'message': '处置结果不能超过2000个字符。'}
    if status in _REPUTATION_TASK_CLOSED_STATUSES and (not result_note):
        return {'ok': False, 'result_required': True, 'message': '完成或忽略任务前，必须填写处置结果。'}
    try:
        if status in _REPUTATION_TASK_CLOSED_STATUSES:
            conn.execute("\n                UPDATE v157_reputation_tasks\n                SET\n                    priority=?,\n                    owner=?,\n                    status=?,\n                    result_note=?,\n                    updated_at=datetime(\n                        'now',\n                        'localtime'\n                    ),\n                    completed_at=CASE\n                        WHEN IFNULL(\n                            completed_at,\n                            ''\n                        )=''\n                        THEN datetime(\n                            'now',\n                            'localtime'\n                        )\n                        ELSE completed_at\n                    END\n                WHERE id=?\n          AND battle_id = ?\n                ", (priority, owner, status, result_note, task_id, battle_id))
        else:
            conn.execute("\n                UPDATE v157_reputation_tasks\n                SET\n                    priority=?,\n                    owner=?,\n                    status=?,\n                    result_note=?,\n                    updated_at=datetime(\n                        'now',\n                        'localtime'\n                    ),\n                    completed_at=''\n                WHERE id=?\n          AND battle_id = ?\n                ", (priority, owner, status, result_note, task_id, battle_id))
        conn.commit()
    except sqlite3.IntegrityError:
        return {'ok': False, 'duplicate': True, 'message': '该对象已经存在另一条未闭环任务。'}
    updated = get_reputation_task_scoped(conn, task_id, battle_id=battle_id)
    return {'ok': True, 'task': updated, 'message': '处置任务已更新。'}

def list_reputation_events_scoped(
    conn,
    q="",
    limit=100,
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    ensure_reputation_tables(conn)

    try:
        limit = int(limit)
    except (TypeError, ValueError):
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

    cols = {
        str(row[1])
        for row in conn.execute(
            "PRAGMA table_info(v156_reputation_events)"
        ).fetchall()
    }

    search_cols = [
        name
        for name in (
            "title",
            "event_type",
            "summary",
            "evidence_note",
            "note",
        )
        if name in cols
    ]

    where_parts = [
        "battle_id = ?",
    ]

    params = [
        battle_id,
    ]

    if q and search_cols:
        where_parts.append(
            "("
            + " OR ".join(
                "IFNULL(" + name + ", '') LIKE ?"
                for name in search_cols
            )
            + ")"
        )

        params.extend(
            ["%" + q + "%"]
            * len(search_cols)
        )

    if "updated_at" in cols:
        order_sql = "updated_at DESC, id DESC"
    elif "created_at" in cols:
        order_sql = "created_at DESC, id DESC"
    elif "event_time" in cols:
        order_sql = "event_time DESC, id DESC"
    else:
        order_sql = "id DESC"

    sql = (
        "SELECT * "
        "FROM v156_reputation_events "
        "WHERE "
        + " AND ".join(where_parts)
        + " ORDER BY "
        + order_sql
        + " LIMIT ?"
    )

    params.append(limit)

    rows = conn.execute(
        sql,
        params,
    ).fetchall()

    return _v155_reputation_rows_dict(rows)

def build_reputation_duplicate_report_scoped(
    conn,
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    ensure_reputation_tables(conn)

    scoped_conn = sqlite3.connect(":memory:")
    scoped_conn.row_factory = sqlite3.Row

    try:
        ensure_reputation_tables(scoped_conn)

        source_cols = [
            str(row[1])
            for row in conn.execute(
                "PRAGMA table_info(v156_reputation_subjects)"
            ).fetchall()
        ]

        target_cols = {
            str(row[1])
            for row in scoped_conn.execute(
                "PRAGMA table_info(v156_reputation_subjects)"
            ).fetchall()
        }

        cols = [
            name
            for name in source_cols
            if name in target_cols
        ]

        if not cols:
            return build_reputation_duplicate_report(
                scoped_conn
            )

        quoted = ", ".join(
            '"' + name.replace('"', '""') + '"'
            for name in cols
        )

        rows = conn.execute(
            "SELECT "
            + quoted
            + " FROM v156_reputation_subjects "
              "WHERE battle_id = ?",
            (
                battle_id,
            ),
        ).fetchall()

        placeholders = ", ".join(
            ["?"] * len(cols)
        )

        if rows:
            scoped_conn.executemany(
                "INSERT INTO v156_reputation_subjects ("
                + quoted
                + ") VALUES ("
                + placeholders
                + ")",
                [
                    tuple(row)
                    for row in rows
                ],
            )

        scoped_conn.commit()

        return build_reputation_duplicate_report(
            scoped_conn
        )

    finally:
        scoped_conn.close()

def merge_reputation_subjects_scoped(
    conn,
    keep_id,
    merge_id,
    *,
    battle_id,
):
    battle_id = _v155_reputation_positive_battle_id(battle_id)

    try:
        keep_id = int(keep_id)
        merge_id = int(merge_id)
    except (TypeError, ValueError):
        return False

    if (
        keep_id <= 0
        or merge_id <= 0
        or keep_id == merge_id
    ):
        return False

    keep_row = get_reputation_subject_scoped(
        conn,
        keep_id,
        battle_id=battle_id,
    )

    merge_row = get_reputation_subject_scoped(
        conn,
        merge_id,
        battle_id=battle_id,
    )

    if (
        keep_row is None
        or merge_row is None
    ):
        return False

    unsafe_relation = conn.execute(
        """
        SELECT 1
        FROM v156_reputation_event_relations AS r
        LEFT JOIN v156_reputation_events AS e
          ON e.id = r.event_id
         AND e.battle_id = r.battle_id
        WHERE r.subject_id IN (?, ?)
          AND (
                r.battle_id IS NULL
             OR r.battle_id <> ?
             OR e.id IS NULL
             OR e.battle_id IS NULL
             OR e.battle_id <> ?
          )
        LIMIT 1
        """,
        (
            keep_id,
            merge_id,
            battle_id,
            battle_id,
        ),
    ).fetchone()

    if unsafe_relation is not None:
        return False

    return merge_reputation_subjects(
        conn,
        keep_id=keep_id,
        merge_id=merge_id,
    )
