from __future__ import annotations

from typing import Any, Dict, List


def ensure_command_action_log_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v15_command_action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_key TEXT DEFAULT '',
            action_label TEXT DEFAULT '',
            status TEXT DEFAULT '',
            status_label TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    conn.commit()


def save_command_action_log(
    conn,
    action_key: str,
    action_label: str,
    status: str,
    note: str = "",
) -> None:
    ensure_command_action_log_table(conn)

    action_key = str(action_key or "").strip()
    action_label = str(action_label or "").strip()
    status = str(status or "").strip()
    note = str(note or "").strip()

    if not action_key:
        return

    conn.execute(
        """
        INSERT INTO v15_command_action_logs (
            action_key,
            action_label,
            status,
            status_label,
            note,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """,
        (
            action_key,
            action_label,
            status,
            _status_label(status),
            note,
        )
    )

    conn.commit()


def load_command_action_logs(
    conn,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    ensure_command_action_log_table(conn)

    cur = conn.execute(
        """
        SELECT
            action_key,
            action_label,
            status,
            status_label,
            note,
            created_at
        FROM v15_command_action_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    )

    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def load_command_action_logs_by_key(
    conn,
    action_key: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    ensure_command_action_log_table(conn)

    action_key = str(action_key or "").strip()

    cur = conn.execute(
        """
        SELECT
            action_key,
            action_label,
            status,
            status_label,
            note,
            created_at
        FROM v15_command_action_logs
        WHERE action_key = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (
            action_key,
            limit,
        )
    )

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
