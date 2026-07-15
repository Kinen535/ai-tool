from __future__ import annotations

import json
import re
import sqlite3
from typing import Any


AUTH_TABLES = (
    "v158_users",
    "v158_login_logs",
    "v158_action_logs",
)

AUTH_SCHEMA_SQL = "CREATE TABLE IF NOT EXISTS v158_users (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n\n    username TEXT NOT NULL COLLATE NOCASE\n        CHECK (username = trim(username))\n        CHECK (length(username) BETWEEN 3 AND 64)\n        CHECK (substr(username, 1, 1) GLOB '[A-Za-z0-9]')\n        CHECK (username NOT GLOB '*[^A-Za-z0-9._-]*'),\n\n    password_hash TEXT NOT NULL\n        CHECK (length(password_hash) >= 60),\n\n    display_name TEXT NOT NULL DEFAULT ''\n        CHECK (length(display_name) <= 100),\n\n    role TEXT NOT NULL\n        CHECK (role IN ('super_admin', 'manager', 'viewer')),\n\n    status TEXT NOT NULL DEFAULT 'active'\n        CHECK (status IN ('active', 'disabled')),\n\n    failed_login_count INTEGER NOT NULL DEFAULT 0\n        CHECK (failed_login_count >= 0),\n\n    locked_until TEXT,\n    last_failed_login_at TEXT,\n    last_login_at TEXT,\n\n    last_login_ip TEXT NOT NULL DEFAULT ''\n        CHECK (length(last_login_ip) <= 64),\n\n    password_changed_at TEXT NOT NULL\n        DEFAULT (datetime('now', 'localtime')),\n\n    must_change_password INTEGER NOT NULL DEFAULT 0\n        CHECK (must_change_password IN (0, 1)),\n\n    session_version INTEGER NOT NULL DEFAULT 1\n        CHECK (session_version >= 1),\n\n    created_at TEXT NOT NULL\n        DEFAULT (datetime('now', 'localtime')),\n\n    updated_at TEXT NOT NULL\n        DEFAULT (datetime('now', 'localtime'))\n);\n\nCREATE UNIQUE INDEX IF NOT EXISTS\n    idx_v158_users_username_unique\nON v158_users(username COLLATE NOCASE);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_users_role_status\nON v158_users(role, status);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_users_locked_until\nON v158_users(locked_until);\nCREATE TABLE IF NOT EXISTS v158_login_logs (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n\n    user_id INTEGER\n        CHECK (\n            user_id IS NULL OR user_id > 0\n        ),\n\n    username_snapshot TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(username_snapshot) <= 64\n        ),\n\n    event_type TEXT NOT NULL\n        CHECK (\n            event_type IN (\n                'login_success',\n                'login_failure',\n                'logout',\n                'account_locked',\n                'account_unlocked',\n                'session_rejected',\n                'password_changed'\n            )\n        ),\n\n    result_status TEXT NOT NULL\n        CHECK (\n            result_status IN (\n                'success',\n                'failure',\n                'blocked'\n            )\n        ),\n\n    reason_code TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(reason_code) <= 64\n        ),\n\n    ip_address TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(ip_address) <= 64\n        ),\n\n    user_agent TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(user_agent) <= 1000\n        ),\n\n    request_path TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(request_path) <= 255\n        ),\n\n    session_version INTEGER\n        CHECK (\n            session_version IS NULL OR session_version >= 1\n        ),\n\n    created_at TEXT NOT NULL\n        DEFAULT (datetime('now', 'localtime'))\n);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_login_logs_user_time\nON v158_login_logs(user_id, created_at);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_login_logs_username_time\nON v158_login_logs(username_snapshot, created_at);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_login_logs_ip_time\nON v158_login_logs(ip_address, created_at);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_login_logs_event_time\nON v158_login_logs(event_type, created_at);\nCREATE TABLE IF NOT EXISTS v158_action_logs (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n\n    user_id INTEGER\n        CHECK (\n            user_id IS NULL OR user_id > 0\n        ),\n\n    username_snapshot TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(username_snapshot) <= 64\n        ),\n\n    role_snapshot TEXT NOT NULL DEFAULT ''\n        CHECK (\n            role_snapshot IN (\n                '',\n                'super_admin',\n                'manager',\n                'viewer',\n                'system'\n            )\n        ),\n\n    battle_id INTEGER\n        CHECK (\n            battle_id IS NULL OR battle_id > 0\n        ),\n\n    request_id TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(request_id) <= 64\n        ),\n\n    action_key TEXT NOT NULL\n        CHECK (\n            length(action_key) BETWEEN 2 AND 100\n        ),\n\n    action_label TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(action_label) <= 200\n        ),\n\n    target_type TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(target_type) <= 100\n        ),\n\n    target_id TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(target_id) <= 100\n        ),\n\n    target_label TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(target_label) <= 300\n        ),\n\n    result_status TEXT NOT NULL\n        CHECK (\n            result_status IN (\n                'success',\n                'failure',\n                'blocked'\n            )\n        ),\n\n    before_data TEXT NOT NULL DEFAULT ''\n        CHECK (\n            before_data = ''\n            OR json_valid(before_data)\n        ),\n\n    after_data TEXT NOT NULL DEFAULT ''\n        CHECK (\n            after_data = ''\n            OR json_valid(after_data)\n        ),\n\n    reason TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(reason) <= 2000\n        ),\n\n    request_method TEXT NOT NULL DEFAULT ''\n        CHECK (\n            request_method IN (\n                '',\n                'GET',\n                'POST',\n                'PUT',\n                'PATCH',\n                'DELETE',\n                'CLI',\n                'SYSTEM'\n            )\n        ),\n\n    request_path TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(request_path) <= 500\n        ),\n\n    ip_address TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(ip_address) <= 64\n        ),\n\n    user_agent TEXT NOT NULL DEFAULT ''\n        CHECK (\n            length(user_agent) <= 1000\n        ),\n\n    created_at TEXT NOT NULL\n        DEFAULT (datetime('now', 'localtime'))\n);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_action_logs_user_time\nON v158_action_logs(user_id, created_at);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_action_logs_action_time\nON v158_action_logs(action_key, created_at);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_action_logs_target_time\nON v158_action_logs(target_type, target_id, created_at);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_action_logs_battle_time\nON v158_action_logs(battle_id, created_at);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_action_logs_request\nON v158_action_logs(request_id);\n\nCREATE INDEX IF NOT EXISTS\n    idx_v158_action_logs_result_time\nON v158_action_logs(result_status, created_at);\n"

USERNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$"
)

VALID_ROLES = {
    "super_admin",
    "manager",
    "viewer",
}

VALID_USER_STATUSES = {
    "active",
    "disabled",
}

VALID_LOGIN_EVENTS = {
    "login_success",
    "login_failure",
    "logout",
    "account_locked",
    "account_unlocked",
    "session_rejected",
    "password_changed",
}

VALID_RESULTS = {
    "success",
    "failure",
    "blocked",
}


def ensure_v158_auth_tables(
    conn: sqlite3.Connection,
) -> None:
    """以单一事务幂等创建 V15.8 认证基础表和索引。"""

    if conn.in_transaction:
        raise RuntimeError(
            "认证表初始化前存在未提交事务，禁止隐式提交。"
        )

    migration_sql = (
        "BEGIN IMMEDIATE;\n"
        + AUTH_SCHEMA_SQL
        + "\nCOMMIT;"
    )

    try:
        conn.executescript(migration_sql)
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise


def get_v158_auth_schema_status(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """只读检查认证表和索引是否完整。"""

    table_rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name LIKE 'v158_%'
        ORDER BY name
        """
    ).fetchall()

    existing_tables = {
        str(row[0])
        for row in table_rows
    }

    missing_tables = [
        table
        for table in AUTH_TABLES
        if table not in existing_tables
    ]

    index_counts: dict[str, int] = {}

    for table in AUTH_TABLES:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='index'
              AND tbl_name=?
            """,
            (table,),
        ).fetchone()[0]

        index_counts[table] = int(count or 0)

    expected_index_counts = {
        "v158_users": 3,
        "v158_login_logs": 4,
        "v158_action_logs": 6,
    }

    index_ok = all(
        index_counts.get(table, 0) >= expected
        for table, expected in expected_index_counts.items()
    )

    return {
        "ok": not missing_tables and index_ok,
        "existing_tables": sorted(existing_tables),
        "missing_tables": missing_tables,
        "index_counts": index_counts,
        "expected_index_counts": expected_index_counts,
    }


def normalize_username(value: Any) -> str:
    return str(value or "").strip()


def validate_username(username: str) -> None:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "用户名必须为3至64位，"
            "以字母或数字开头，"
            "且只允许字母、数字、点、下划线和连字符。"
        )


def validate_role(role: str) -> None:
    if role not in VALID_ROLES:
        raise ValueError("不支持的用户角色。")


def validate_user_status(status: str) -> None:
    if status not in VALID_USER_STATUSES:
        raise ValueError("不支持的用户状态。")


def get_user_by_id(
    conn: sqlite3.Connection,
    user_id: int,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM v158_users
        WHERE id=?
        """,
        (int(user_id),),
    ).fetchone()

    return dict(row) if row else None


def get_user_by_username(
    conn: sqlite3.Connection,
    username: str,
) -> dict[str, Any] | None:
    username = normalize_username(username)

    row = conn.execute(
        """
        SELECT *
        FROM v158_users
        WHERE username = ? COLLATE NOCASE
        """,
        (username,),
    ).fetchone()

    return dict(row) if row else None


def create_user(
    conn: sqlite3.Connection,
    *,
    username: str,
    password_hash: str,
    display_name: str,
    role: str,
    status: str = "active",
    must_change_password: bool = True,
) -> int:
    username = normalize_username(username)
    password_hash = str(password_hash or "")
    display_name = str(display_name or "").strip()
    role = str(role or "").strip()
    status = str(status or "").strip()

    validate_username(username)
    validate_role(role)
    validate_user_status(status)

    if len(password_hash) < 60:
        raise ValueError("密码哈希格式无效。")

    cursor = conn.execute(
        """
        INSERT INTO v158_users (
            username,
            password_hash,
            display_name,
            role,
            status,
            must_change_password
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            password_hash,
            display_name[:100],
            role,
            status,
            1 if must_change_password else 0,
        ),
    )

    return int(cursor.lastrowid)


def _json_text(value: Any) -> str:
    if value is None or value == "":
        return ""

    if isinstance(value, str):
        json.loads(value)
        return value

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def record_login_event(
    conn: sqlite3.Connection,
    *,
    user_id: int | None,
    username_snapshot: str,
    event_type: str,
    result_status: str,
    reason_code: str = "",
    ip_address: str = "",
    user_agent: str = "",
    request_path: str = "",
    session_version: int | None = None,
) -> int:
    if event_type not in VALID_LOGIN_EVENTS:
        raise ValueError("不支持的登录事件类型。")

    if result_status not in VALID_RESULTS:
        raise ValueError("不支持的登录结果状态。")

    cursor = conn.execute(
        """
        INSERT INTO v158_login_logs (
            user_id,
            username_snapshot,
            event_type,
            result_status,
            reason_code,
            ip_address,
            user_agent,
            request_path,
            session_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id) if user_id is not None else None,
            str(username_snapshot or "")[:64],
            event_type,
            result_status,
            str(reason_code or "")[:64],
            str(ip_address or "")[:64],
            str(user_agent or "")[:1000],
            str(request_path or "")[:255],
            (
                int(session_version)
                if session_version is not None
                else None
            ),
        ),
    )

    return int(cursor.lastrowid)


def record_action_log(
    conn: sqlite3.Connection,
    *,
    user_id: int | None,
    username_snapshot: str,
    role_snapshot: str,
    action_key: str,
    result_status: str,
    battle_id: int | None = None,
    request_id: str = "",
    action_label: str = "",
    target_type: str = "",
    target_id: str = "",
    target_label: str = "",
    before_data: Any = None,
    after_data: Any = None,
    reason: str = "",
    request_method: str = "",
    request_path: str = "",
    ip_address: str = "",
    user_agent: str = "",
) -> int:
    action_key = str(action_key or "").strip()

    if not 2 <= len(action_key) <= 100:
        raise ValueError("操作键长度必须为2至100位。")

    if result_status not in VALID_RESULTS:
        raise ValueError("不支持的操作结果状态。")

    cursor = conn.execute(
        """
        INSERT INTO v158_action_logs (
            user_id,
            username_snapshot,
            role_snapshot,
            battle_id,
            request_id,
            action_key,
            action_label,
            target_type,
            target_id,
            target_label,
            result_status,
            before_data,
            after_data,
            reason,
            request_method,
            request_path,
            ip_address,
            user_agent
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            int(user_id) if user_id is not None else None,
            str(username_snapshot or "")[:64],
            str(role_snapshot or "")[:20],
            int(battle_id) if battle_id is not None else None,
            str(request_id or "")[:64],
            action_key,
            str(action_label or "")[:200],
            str(target_type or "")[:100],
            str(target_id or "")[:100],
            str(target_label or "")[:300],
            result_status,
            _json_text(before_data),
            _json_text(after_data),
            str(reason or "")[:2000],
            str(request_method or "")[:10],
            str(request_path or "")[:500],
            str(ip_address or "")[:64],
            str(user_agent or "")[:1000],
        ),
    )

    return int(cursor.lastrowid)


def get_user_lock_state(
    conn: sqlite3.Connection,
    user_id: int,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            id,
            failed_login_count,
            locked_until,
            session_version,
            CASE
                WHEN locked_until IS NOT NULL
                 AND datetime(locked_until) >
                     datetime('now', 'localtime')
                THEN 1
                ELSE 0
            END AS is_locked
        FROM v158_users
        WHERE id=?
        """,
        (int(user_id),),
    ).fetchone()

    return dict(row) if row else None


def register_login_failure(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    lock_after: int = 5,
    lock_minutes: int = 15,
) -> dict[str, Any]:
    lock_after = max(int(lock_after), 1)
    lock_minutes = max(int(lock_minutes), 1)

    current = get_user_lock_state(conn, user_id)

    if not current:
        raise ValueError("用户不存在。")

    next_count = int(
        current.get("failed_login_count") or 0
    ) + 1

    should_lock = next_count >= lock_after
    was_locked = bool(current.get("is_locked"))

    locked_until = current.get("locked_until")

    if should_lock and not was_locked:
        locked_until = conn.execute(
            """
            SELECT datetime(
                'now',
                'localtime',
                ?
            )
            """,
            (f"+{lock_minutes} minutes",),
        ).fetchone()[0]

    conn.execute(
        """
        UPDATE v158_users
        SET
            failed_login_count=?,
            last_failed_login_at=
                datetime('now', 'localtime'),
            locked_until=?,
            session_version=
                CASE
                    WHEN ?=1 AND ?=0
                    THEN session_version + 1
                    ELSE session_version
                END,
            updated_at=datetime('now', 'localtime')
        WHERE id=?
        """,
        (
            next_count,
            locked_until,
            1 if should_lock else 0,
            1 if was_locked else 0,
            int(user_id),
        ),
    )

    updated = get_user_lock_state(conn, user_id)

    if not updated:
        raise RuntimeError("登录失败状态更新后用户丢失。")

    updated["just_locked"] = bool(
        should_lock and not was_locked
    )

    return updated


def register_login_success(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    ip_address: str = "",
) -> dict[str, Any]:
    current = get_user_lock_state(conn, user_id)

    if not current:
        raise ValueError("用户不存在。")

    if current.get("is_locked"):
        raise PermissionError("账号仍处于锁定状态。")

    conn.execute(
        """
        UPDATE v158_users
        SET
            failed_login_count=0,
            locked_until=NULL,
            last_login_at=datetime('now', 'localtime'),
            last_login_ip=?,
            updated_at=datetime('now', 'localtime')
        WHERE id=?
        """,
        (
            str(ip_address or "")[:64],
            int(user_id),
        ),
    )

    user = get_user_by_id(conn, user_id)

    if not user:
        raise RuntimeError("登录成功状态更新后用户丢失。")

    return user


def unlock_user(
    conn: sqlite3.Connection,
    *,
    user_id: int,
) -> dict[str, Any]:
    cursor = conn.execute(
        """
        UPDATE v158_users
        SET
            failed_login_count=0,
            locked_until=NULL,
            session_version=session_version + 1,
            updated_at=datetime('now', 'localtime')
        WHERE id=?
        """,
        (int(user_id),),
    )

    if cursor.rowcount != 1:
        raise ValueError("用户不存在。")

    user = get_user_by_id(conn, user_id)

    if not user:
        raise RuntimeError("解锁后用户丢失。")

    return user


def change_user_password(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    password_hash: str,
    must_change_password: bool = False,
) -> dict[str, Any]:
    password_hash = str(password_hash or "")

    if len(password_hash) < 60:
        raise ValueError("密码哈希格式无效。")

    cursor = conn.execute(
        """
        UPDATE v158_users
        SET
            password_hash=?,
            password_changed_at=
                datetime('now', 'localtime'),
            must_change_password=?,
            failed_login_count=0,
            locked_until=NULL,
            session_version=session_version + 1,
            updated_at=datetime('now', 'localtime')
        WHERE id=?
        """,
        (
            password_hash,
            1 if must_change_password else 0,
            int(user_id),
        ),
    )

    if cursor.rowcount != 1:
        raise ValueError("用户不存在。")

    user = get_user_by_id(conn, user_id)

    if not user:
        raise RuntimeError("密码修改后用户丢失。")

    return user


def count_active_super_admins(
    conn: sqlite3.Connection,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM v158_users
        WHERE role='super_admin'
          AND status='active'
        """
    ).fetchone()

    return int(row[0] or 0) if row else 0


def update_user_access(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    role: str,
    status: str,
) -> dict[str, Any]:
    role = str(role or "").strip()
    status = str(status or "").strip()

    validate_role(role)
    validate_user_status(status)

    current = get_user_by_id(conn, user_id)

    if not current:
        raise ValueError("用户不存在。")

    removes_active_super_admin = (
        current.get("role") == "super_admin"
        and current.get("status") == "active"
        and (
            role != "super_admin"
            or status != "active"
        )
    )

    if (
        removes_active_super_admin
        and count_active_super_admins(conn) <= 1
    ):
        raise ValueError(
            "不能停用或降级最后一个有效超级管理员。"
        )

    changed = (
        current.get("role") != role
        or current.get("status") != status
    )

    conn.execute(
        """
        UPDATE v158_users
        SET
            role=?,
            status=?,
            session_version=
                CASE
                    WHEN ?=1
                    THEN session_version + 1
                    ELSE session_version
                END,
            updated_at=datetime('now', 'localtime')
        WHERE id=?
        """,
        (
            role,
            status,
            1 if changed else 0,
            int(user_id),
        ),
    )

    user = get_user_by_id(conn, user_id)

    if not user:
        raise RuntimeError("权限更新后用户丢失。")

    user["access_changed"] = changed
    return user
