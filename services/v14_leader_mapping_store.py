from __future__ import annotations

from typing import Any, Dict


def ensure_leader_mapping_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v14_leader_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT UNIQUE,
            leader_name TEXT DEFAULT '',
            leader_role TEXT DEFAULT '组长',
            note TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    conn.commit()


def load_leader_mappings(conn) -> Dict[str, Dict[str, Any]]:
    ensure_leader_mapping_table(conn)

    cur = conn.execute(
        """
        SELECT
            group_name,
            leader_name,
            leader_role,
            note,
            is_active,
            updated_at
        FROM v14_leader_mappings
        WHERE is_active = 1
        """
    )

    cols = [desc[0] for desc in cur.description]
    result: Dict[str, Dict[str, Any]] = {}

    for row in cur.fetchall():
        item = dict(zip(cols, row))
        group_name = str(item.get("group_name") or "").strip()

        if not group_name:
            continue

        result[group_name] = item

    return result


def upsert_leader_mapping(
    conn,
    group_name: str,
    leader_name: str,
    leader_role: str = "组长",
    note: str = "",
) -> None:
    ensure_leader_mapping_table(conn)

    group_name = str(group_name or "").strip()
    leader_name = str(leader_name or "").strip()
    leader_role = str(leader_role or "组长").strip()
    note = str(note or "").strip()

    if not group_name:
        return

    conn.execute(
        """
        INSERT INTO v14_leader_mappings (
            group_name,
            leader_name,
            leader_role,
            note,
            is_active,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, 1, datetime('now', 'localtime'), datetime('now', 'localtime'))
        ON CONFLICT(group_name) DO UPDATE SET
            leader_name = excluded.leader_name,
            leader_role = excluded.leader_role,
            note = excluded.note,
            is_active = 1,
            updated_at = datetime('now', 'localtime')
        """,
        (
            group_name,
            leader_name,
            leader_role,
            note,
        )
    )
    conn.commit()


def deactivate_leader_mapping(conn, group_name: str) -> None:
    ensure_leader_mapping_table(conn)

    group_name = str(group_name or "").strip()

    if not group_name:
        return

    conn.execute(
        """
        UPDATE v14_leader_mappings
        SET
            is_active = 0,
            updated_at = datetime('now', 'localtime')
        WHERE group_name = ?
        """,
        (group_name,)
    )
    conn.commit()
