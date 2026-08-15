from __future__ import annotations

from typing import Any, Dict, List


def ensure_command_action_log_table(conn) -> None:
    conn.execute("\n        CREATE TABLE IF NOT EXISTS v15_command_action_logs (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            action_key TEXT DEFAULT '',\n            action_label TEXT DEFAULT '',\n            status TEXT DEFAULT '',\n            status_label TEXT DEFAULT '',\n            note TEXT DEFAULT '',\n            created_at TEXT DEFAULT (datetime('now', 'localtime')),\n            battle_id INTEGER,\n            FOREIGN KEY (battle_id)\n                REFERENCES battles(id)\n                ON UPDATE RESTRICT\n                ON DELETE RESTRICT\n        )\n    ")
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_p0s04_v15_command_action_logs_battle_lookup\n        ON v15_command_action_logs (\n            battle_id,\n            action_key,\n            id\n        )\n    ')
    conn.commit()


def save_command_action_log(conn, action_key: str, action_label: str, status: str, note: str='', *, battle_id: int) -> None:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_command_action_log_table(conn)
    action_key = str(action_key or '').strip()
    action_label = str(action_label or '').strip()
    status = str(status or '').strip()
    note = str(note or '').strip()
    if not action_key:
        return
    conn.execute("\n        INSERT INTO v15_command_action_logs (\n            battle_id,\n            action_key,\n            action_label,\n            status,\n            status_label,\n            note,\n            created_at\n        )\n        VALUES (\n            ?,?, ?, ?, ?, ?, datetime('now', 'localtime'))\n        ", (battle_id, action_key, action_label, status, _status_label(status), note))
    conn.commit()


def load_command_action_logs(conn, limit: int=20, *, battle_id: int) -> List[Dict[str, Any]]:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_command_action_log_table(conn)
    cur = conn.execute('\n        SELECT\n            action_key,\n            action_label,\n            status,\n            status_label,\n            note,\n            created_at\n        FROM v15_command_action_logs\n        \n        WHERE battle_id = ?\n        ORDER BY id DESC\n        LIMIT ?\n        ', (battle_id, limit))
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def load_command_action_logs_by_key(conn, action_key: str, limit: int=20, *, battle_id: int) -> List[Dict[str, Any]]:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_command_action_log_table(conn)
    action_key = str(action_key or '').strip()
    cur = conn.execute('\n        SELECT\n            action_key,\n            action_label,\n            status,\n            status_label,\n            note,\n            created_at\n        FROM v15_command_action_logs\n        WHERE battle_id = ? AND action_key = ?\n        ORDER BY id DESC\n        LIMIT ?\n        ', (battle_id, action_key, limit))
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _status_label(status: str) -> str:
    labels = {
        "started": "开始处理",
        "done": "已完成",
        "paused": "暂缓处理",
        "blocked": "被阻断",
    }

    return labels.get(status, "未知状态")
