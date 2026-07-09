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
