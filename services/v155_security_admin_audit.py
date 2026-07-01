from __future__ import annotations

import sqlite3
from typing import Any


def ensure_admin_audit_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_admin_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_ip TEXT,
            user_agent TEXT,
            action_key TEXT,
            action_label TEXT,
            result_status TEXT,
            note TEXT,
            request_path TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_v155_security_admin_audit_created
        ON v155_security_admin_audit_logs(created_at)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_v155_security_admin_audit_action
        ON v155_security_admin_audit_logs(action_key)
        """
    )

    conn.commit()


def record_admin_action(
    conn: sqlite3.Connection,
    *,
    admin_ip: str,
    user_agent: str,
    action_key: str,
    action_label: str,
    result_status: str = "success",
    note: str = "",
    request_path: str = "",
) -> None:
    ensure_admin_audit_table(conn)

    conn.execute(
        """
        INSERT INTO v155_security_admin_audit_logs (
            admin_ip,
            user_agent,
            action_key,
            action_label,
            result_status,
            note,
            request_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(admin_ip or "")[:120],
            str(user_agent or "")[:500],
            str(action_key or "")[:120],
            str(action_label or "")[:200],
            str(result_status or "")[:50],
            str(note or "")[:1000],
            str(request_path or "")[:300],
        ),
    )

    conn.commit()


def list_admin_actions(
    conn: sqlite3.Connection,
    *,
    page: int = 1,
    per_page: int = 30,
) -> dict[str, Any]:
    ensure_admin_audit_table(conn)

    page = max(int(page or 1), 1)
    per_page = max(min(int(per_page or 30), 100), 10)
    offset = (page - 1) * per_page

    total = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_security_admin_audit_logs
        """
    ).fetchone()[0]

    rows = conn.execute(
        """
        SELECT
            id,
            admin_ip,
            user_agent,
            action_key,
            action_label,
            result_status,
            note,
            request_path,
            created_at
        FROM v155_security_admin_audit_logs
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (per_page, offset),
    ).fetchall()

    total_pages = max((total + per_page - 1) // per_page, 1)

    return {
        "rows": [dict(row) for row in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": max(page - 1, 1),
        "next_page": min(page + 1, total_pages),
    }
