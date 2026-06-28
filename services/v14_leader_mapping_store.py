from __future__ import annotations

from typing import Any, Dict, List, Optional


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

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v14_leader_mapping_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT,
            action TEXT,
            old_leader_name TEXT DEFAULT '',
            new_leader_name TEXT DEFAULT '',
            old_leader_role TEXT DEFAULT '',
            new_leader_role TEXT DEFAULT '',
            old_is_active INTEGER DEFAULT 0,
            new_is_active INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
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


def load_leader_mapping_logs(conn, limit: int = 20) -> List[Dict[str, Any]]:
    ensure_leader_mapping_table(conn)

    cur = conn.execute(
        """
        SELECT
            group_name,
            action,
            old_leader_name,
            new_leader_name,
            old_leader_role,
            new_leader_role,
            old_is_active,
            new_is_active,
            note,
            created_at
        FROM v14_leader_mapping_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    )

    cols = [desc[0] for desc in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]

    for row in rows:
        row["action_label"] = _action_label(row.get("action"))
        row["change_text"] = _change_text(row)

    return rows


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

    old = _load_mapping_row(conn, group_name)

    if old and int(old.get("is_active") or 0) == 0:
        action = "reactivate_manual"
    elif old:
        action = "update_manual"
    else:
        action = "create_manual"

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

    _insert_mapping_log(
        conn=conn,
        group_name=group_name,
        action=action,
        old=old,
        new_leader_name=leader_name,
        new_leader_role=leader_role,
        new_is_active=1,
        note=note,
    )

    conn.commit()


def deactivate_leader_mapping(conn, group_name: str) -> None:
    ensure_leader_mapping_table(conn)

    group_name = str(group_name or "").strip()

    if not group_name:
        return

    old = _load_mapping_row(conn, group_name)

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

    _insert_mapping_log(
        conn=conn,
        group_name=group_name,
        action="delete_manual",
        old=old,
        new_leader_name="",
        new_leader_role="",
        new_is_active=0,
        note="清除手动指定",
    )

    conn.commit()


def _load_mapping_row(conn, group_name: str) -> Optional[Dict[str, Any]]:
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
        WHERE group_name = ?
        LIMIT 1
        """,
        (group_name,)
    )

    row = cur.fetchone()

    if not row:
        return None

    cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


def _insert_mapping_log(
    conn,
    group_name: str,
    action: str,
    old: Optional[Dict[str, Any]],
    new_leader_name: str,
    new_leader_role: str,
    new_is_active: int,
    note: str,
) -> None:
    old = old or {}

    conn.execute(
        """
        INSERT INTO v14_leader_mapping_logs (
            group_name,
            action,
            old_leader_name,
            new_leader_name,
            old_leader_role,
            new_leader_role,
            old_is_active,
            new_is_active,
            note,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """,
        (
            group_name,
            action,
            str(old.get("leader_name") or ""),
            str(new_leader_name or ""),
            str(old.get("leader_role") or ""),
            str(new_leader_role or ""),
            int(old.get("is_active") or 0),
            int(new_is_active or 0),
            str(note or ""),
        )
    )


def _action_label(action: Any) -> str:
    action = str(action or "").strip()

    labels = {
        "create_manual": "新增手动指定",
        "update_manual": "修改手动指定",
        "reactivate_manual": "恢复手动指定",
        "delete_manual": "清除手动指定",
    }

    return labels.get(action, action or "未知操作")


def _change_text(row: Dict[str, Any]) -> str:
    action = str(row.get("action") or "").strip()

    old_name = str(row.get("old_leader_name") or "无").strip()
    new_name = str(row.get("new_leader_name") or "无").strip()

    if action == "delete_manual":
        return f"{old_name} → 已清除"

    if action in ("create_manual", "reactivate_manual"):
        return f"无 → {new_name}"

    if action == "update_manual":
        return f"{old_name} → {new_name}"

    return f"{old_name} → {new_name}"
