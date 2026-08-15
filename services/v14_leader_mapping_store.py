from __future__ import annotations

from typing import Any, Dict, List, Optional


def ensure_leader_mapping_table(conn) -> None:
    conn.execute("\n        CREATE TABLE IF NOT EXISTS v14_leader_mappings (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            group_name TEXT,\n            leader_name TEXT DEFAULT '',\n            leader_role TEXT DEFAULT '组长',\n            note TEXT DEFAULT '',\n            is_active INTEGER DEFAULT 1,\n            created_at TEXT DEFAULT (datetime('now', 'localtime')),\n            updated_at TEXT DEFAULT (datetime('now', 'localtime')),\n            battle_id INTEGER,\n            FOREIGN KEY (battle_id)\n                REFERENCES battles(id)\n                ON UPDATE RESTRICT\n                ON DELETE RESTRICT\n        )\n    ")
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_p0s04_v14_leader_mappings_battle_lookup\n        ON v14_leader_mappings (\n            battle_id,\n            group_name\n        )\n    ')
    conn.execute('\n        CREATE UNIQUE INDEX IF NOT EXISTS\n        uq_p0s04_v14_leader_mappings_scoped\n        ON v14_leader_mappings (\n            battle_id,\n            group_name\n        )\n        WHERE battle_id IS NOT NULL\n    ')
    conn.execute('\n        CREATE UNIQUE INDEX IF NOT EXISTS\n        uq_p0s04_v14_leader_mappings_legacy_null\n        ON v14_leader_mappings (\n            group_name\n        )\n        WHERE battle_id IS NULL\n    ')
    conn.execute("\n        CREATE TABLE IF NOT EXISTS v14_leader_mapping_logs (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            group_name TEXT,\n            action TEXT,\n            old_leader_name TEXT DEFAULT '',\n            new_leader_name TEXT DEFAULT '',\n            old_leader_role TEXT DEFAULT '',\n            new_leader_role TEXT DEFAULT '',\n            old_is_active INTEGER DEFAULT 0,\n            new_is_active INTEGER DEFAULT 0,\n            note TEXT DEFAULT '',\n            created_at TEXT DEFAULT (datetime('now', 'localtime')),\n            battle_id INTEGER,\n            FOREIGN KEY (battle_id)\n                REFERENCES battles(id)\n                ON UPDATE RESTRICT\n                ON DELETE RESTRICT\n        )\n    ")
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_p0s04_v14_leader_mapping_logs_battle_lookup\n        ON v14_leader_mapping_logs (\n            battle_id,\n            group_name,\n            id\n        )\n    ')
    conn.commit()


def load_leader_mappings(conn, *, battle_id: int) -> Dict[str, Dict[str, Any]]:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_leader_mapping_table(conn)
    cur = conn.execute('\n        SELECT\n            group_name,\n            leader_name,\n            leader_role,\n            note,\n            is_active,\n            updated_at\n        FROM v14_leader_mappings\n        WHERE battle_id = ? AND is_active = 1\n        ', (battle_id,))
    cols = [desc[0] for desc in cur.description]
    result: Dict[str, Dict[str, Any]] = {}
    for row in cur.fetchall():
        item = dict(zip(cols, row))
        group_name = str(item.get('group_name') or '').strip()
        if not group_name:
            continue
        result[group_name] = item
    return result


def load_leader_mapping_logs(conn, limit: int=20, *, battle_id: int) -> List[Dict[str, Any]]:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_leader_mapping_table(conn)
    cur = conn.execute('\n        SELECT\n            group_name,\n            action,\n            old_leader_name,\n            new_leader_name,\n            old_leader_role,\n            new_leader_role,\n            old_is_active,\n            new_is_active,\n            note,\n            created_at\n        FROM v14_leader_mapping_logs\n        \n        WHERE battle_id = ?\n        ORDER BY id DESC\n        LIMIT ?\n        ', (battle_id, limit))
    cols = [desc[0] for desc in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    for row in rows:
        row['action_label'] = _action_label(row.get('action'))
        row['change_text'] = _change_text(row)
    return rows


def upsert_leader_mapping(conn, group_name: str, leader_name: str, leader_role: str='组长', note: str='', *, battle_id: int) -> None:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_leader_mapping_table(conn)
    group_name = str(group_name or '').strip()
    leader_name = str(leader_name or '').strip()
    leader_role = str(leader_role or '组长').strip()
    note = str(note or '').strip()
    if not group_name:
        return
    old = _load_mapping_row(conn, group_name, battle_id=battle_id)
    if old and int(old.get('is_active') or 0) == 0:
        action = 'reactivate_manual'
    elif old:
        action = 'update_manual'
    else:
        action = 'create_manual'
    conn.execute("\n        INSERT INTO v14_leader_mappings (\n            battle_id,\n            group_name,\n            leader_name,\n            leader_role,\n            note,\n            is_active,\n            created_at,\n            updated_at\n        )\n        VALUES (\n            ?,?, ?, ?, ?, 1, datetime('now', 'localtime'), datetime('now', 'localtime'))\n        ON CONFLICT(battle_id, group_name) WHERE battle_id IS NOT NULL DO UPDATE SET\n            leader_name = excluded.leader_name,\n            leader_role = excluded.leader_role,\n            note = excluded.note,\n            is_active = 1,\n            updated_at = datetime('now', 'localtime')\n        ", (battle_id, group_name, leader_name, leader_role, note))
    _insert_mapping_log(conn=conn, group_name=group_name, action=action, old=old, new_leader_name=leader_name, new_leader_role=leader_role, new_is_active=1, note=note, battle_id=battle_id)
    conn.commit()


def deactivate_leader_mapping(conn, group_name: str, *, battle_id: int) -> None:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_leader_mapping_table(conn)
    group_name = str(group_name or '').strip()
    if not group_name:
        return
    old = _load_mapping_row(conn, group_name, battle_id=battle_id)
    conn.execute("\n        UPDATE v14_leader_mappings\n        SET\n            is_active = 0,\n            updated_at = datetime('now', 'localtime')\n        WHERE battle_id = ? AND group_name = ?\n        ", (battle_id, group_name))
    _insert_mapping_log(conn=conn, group_name=group_name, action='delete_manual', old=old, new_leader_name='', new_leader_role='', new_is_active=0, note='清除手动指定', battle_id=battle_id)
    conn.commit()


def _load_mapping_row(conn, group_name: str, *, battle_id: int) -> Optional[Dict[str, Any]]:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    cur = conn.execute('\n        SELECT\n            group_name,\n            leader_name,\n            leader_role,\n            note,\n            is_active,\n            updated_at\n        FROM v14_leader_mappings\n        WHERE battle_id = ? AND group_name = ?\n        LIMIT 1\n        ', (battle_id, group_name))
    row = cur.fetchone()
    if not row:
        return None
    cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


def _insert_mapping_log(conn, group_name: str, action: str, old: Optional[Dict[str, Any]], new_leader_name: str, new_leader_role: str, new_is_active: int, note: str, *, battle_id: int) -> None:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    old = old or {}
    conn.execute("\n        INSERT INTO v14_leader_mapping_logs (\n            battle_id,\n            group_name,\n            action,\n            old_leader_name,\n            new_leader_name,\n            old_leader_role,\n            new_leader_role,\n            old_is_active,\n            new_is_active,\n            note,\n            created_at\n        )\n        VALUES (\n            ?,?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))\n        ", (battle_id, group_name, action, str(old.get('leader_name') or ''), str(new_leader_name or ''), str(old.get('leader_role') or ''), str(new_leader_role or ''), int(old.get('is_active') or 0), int(new_is_active or 0), str(note or '')))


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
