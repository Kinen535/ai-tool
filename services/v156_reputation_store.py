from __future__ import annotations

import sqlite3
from typing import Any


def ensure_reputation_tables(conn: sqlite3.Connection) -> None:
    """
    V15.6 信誉档案库基础表。
    注意：这是独立于当前战场 battle_id 的私有信誉档案库。
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v156_reputation_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_type TEXT DEFAULT 'player',
            display_name TEXT,
            game_id TEXT,
            alias_names TEXT DEFAULT '',
            trust_level TEXT DEFAULT 'unknown',
            risk_level TEXT DEFAULT 'normal',
            status TEXT DEFAULT 'active',
            source_type TEXT DEFAULT 'manual',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v156_reputation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            event_type TEXT DEFAULT 'general',
            impact_level TEXT DEFAULT 'normal',
            status TEXT DEFAULT 'recorded',
            event_time TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            evidence_note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v156_reputation_event_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            subject_id INTEGER,
            relation_role TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_v156_rep_subject_game_id
        ON v156_reputation_subjects(game_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_v156_rep_subject_name
        ON v156_reputation_subjects(display_name)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_v156_rep_event_rel_subject
        ON v156_reputation_event_relations(subject_id)
        """
    )

    conn.commit()


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
        },
        "high_risk_subjects": high_risk_subjects,
        "recent_events": recent_events,
        "recent_relations": recent_relations,
        "stage_tip": stage_tip,
    }
