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
    ensure_reputation_tables(conn)

    q = (q or "").strip()

    if not q:
        return {
            "query": q,
            "subjects": [],
            "events": [],
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
        ORDER BY e.id DESC
        LIMIT 30
        """,
        (like, like, like, like, like),
    ).fetchall()

    return {
        "query": q,
        "subjects": subjects,
        "events": events,
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
