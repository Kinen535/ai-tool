from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, Tuple


DEFAULT_CONFIG = {
    "archive_read_only": "0",
    "search_quota_enabled": "1",
    "daily_search_limit": "120",
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_runtime_guard(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_runtime_config (
            config_key TEXT PRIMARY KEY,
            config_value TEXT,
            updated_at TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_search_quota (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            path TEXT,
            query_string TEXT,
            user_agent TEXT,
            created_at TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_guard_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            method TEXT,
            path TEXT,
            query_string TEXT,
            guard_type TEXT,
            reason TEXT,
            user_agent TEXT,
            created_at TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_ip_whitelist (
            ip TEXT PRIMARY KEY,
            note TEXT,
            created_at TEXT
        )
        """
    )

    for key, value in DEFAULT_CONFIG.items():
        row = conn.execute(
            "SELECT config_key FROM v155_security_runtime_config WHERE config_key=?",
            (key,),
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO v155_security_runtime_config
                (config_key, config_value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, value, now_str()),
            )

    for ip, note in [
        ("127.0.0.1", "服务器本机测试"),
        ("::1", "服务器本机测试"),
    ]:
        row = conn.execute(
            "SELECT ip FROM v155_security_ip_whitelist WHERE ip=?",
            (ip,),
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO v155_security_ip_whitelist
                (ip, note, created_at)
                VALUES (?, ?, ?)
                """,
                (ip, note, now_str()),
            )

    conn.commit()


def get_client_ip(req) -> str:
    forwarded = req.headers.get("X-Forwarded-For", "").strip()

    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = req.headers.get("X-Real-IP", "").strip()

    if real_ip:
        return real_ip

    return str(req.remote_addr or "").strip()


def is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "open"}


def get_config_map(conn: sqlite3.Connection) -> Dict[str, str]:
    init_runtime_guard(conn)

    rows = conn.execute(
        "SELECT config_key, config_value FROM v155_security_runtime_config"
    ).fetchall()

    config = dict(DEFAULT_CONFIG)

    for row in rows:
        config[row["config_key"]] = row["config_value"]

    return config


def update_guard_config(conn: sqlite3.Connection, key: str, value: str) -> None:
    init_runtime_guard(conn)

    if key not in DEFAULT_CONFIG:
        raise ValueError(f"Unsupported config key: {key}")

    conn.execute(
        """
        INSERT INTO v155_security_runtime_config
        (config_key, config_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(config_key)
        DO UPDATE SET
            config_value=excluded.config_value,
            updated_at=excluded.updated_at
        """,
        (key, str(value), now_str()),
    )

    conn.commit()


def is_ip_whitelisted(conn: sqlite3.Connection, ip: str) -> bool:
    init_runtime_guard(conn)

    row = conn.execute(
        "SELECT ip FROM v155_security_ip_whitelist WHERE ip=?",
        (ip,),
    ).fetchone()

    return bool(row)


def add_whitelist_ip(conn: sqlite3.Connection, ip: str, note: str = "") -> None:
    init_runtime_guard(conn)

    ip = str(ip or "").strip()
    note = str(note or "").strip()

    if not ip:
        return

    conn.execute(
        """
        INSERT INTO v155_security_ip_whitelist
        (ip, note, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(ip)
        DO UPDATE SET note=excluded.note
        """,
        (ip, note, now_str()),
    )

    conn.commit()


def remove_whitelist_ip(conn: sqlite3.Connection, ip: str) -> None:
    init_runtime_guard(conn)

    ip = str(ip or "").strip()

    if ip in {"127.0.0.1", "::1"}:
        return

    conn.execute(
        "DELETE FROM v155_security_ip_whitelist WHERE ip=?",
        (ip,),
    )

    conn.commit()


def record_guard_block(
    conn: sqlite3.Connection,
    ip: str,
    method: str,
    path: str,
    query_string: str,
    guard_type: str,
    reason: str,
    user_agent: str,
) -> None:
    init_runtime_guard(conn)

    conn.execute(
        """
        INSERT INTO v155_security_guard_blocks
        (ip, method, path, query_string, guard_type, reason, user_agent, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ip,
            method,
            path,
            query_string,
            guard_type,
            reason,
            user_agent,
            now_str(),
        ),
    )

    conn.commit()


def check_read_only(
    conn: sqlite3.Connection,
    ip: str,
    method: str,
    path: str,
    query_string: str = "",
    user_agent: str = "",
) -> Tuple[bool, str, int]:
    config = get_config_map(conn)

    if not is_truthy(config.get("archive_read_only")):
        return True, "", 200

    method = str(method or "").upper()
    path = str(path or "")

    write_methods = {"POST", "PUT", "PATCH", "DELETE"}

    protected_prefixes = (
        "/archives",
        "/archive_",
    )

    if method in write_methods and path.startswith(protected_prefixes):
        reason = "档案库只读模式已开启，写入请求被拦截"

        record_guard_block(
            conn,
            ip,
            method,
            path,
            query_string,
            "read_only",
            reason,
            user_agent,
        )

        return False, reason, 423

    return True, "", 200


def check_search_quota(
    conn: sqlite3.Connection,
    ip: str,
    method: str,
    path: str,
    query_string: str = "",
    user_agent: str = "",
) -> Tuple[bool, str, int]:
    config = get_config_map(conn)

    if not is_truthy(config.get("search_quota_enabled")):
        return True, "", 200

    if is_ip_whitelisted(conn, ip):
        return True, "", 200

    method = str(method or "").upper()
    path = str(path or "")

    search_paths = (
        "/archives/search",
        "/archive_search",
    )

    if method != "GET" or not path.startswith(search_paths):
        return True, "", 200

    try:
        daily_limit = int(config.get("daily_search_limit", "120"))
    except Exception:
        daily_limit = 120

    if daily_limit <= 0:
        daily_limit = 120

    conn.execute(
        """
        DELETE FROM v155_security_search_quota
        WHERE created_at < datetime('now', 'localtime', '-3 days')
        """
    )

    current_count = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM v155_security_search_quota
        WHERE ip=?
          AND created_at >= datetime('now', 'localtime', '-24 hours')
        """,
        (ip,),
    ).fetchone()["c"]

    if int(current_count or 0) >= daily_limit:
        reason = f"搜索额度超限：24小时已搜索 {current_count} 次，限制 {daily_limit} 次"

        record_guard_block(
            conn,
            ip,
            method,
            path,
            query_string,
            "search_quota",
            reason,
            user_agent,
        )

        return False, reason, 429

    conn.execute(
        """
        INSERT INTO v155_security_search_quota
        (ip, path, query_string, user_agent, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            ip,
            path,
            query_string,
            user_agent,
            now_str(),
        ),
    )

    conn.commit()

    return True, "", 200


def build_guard_report(conn: sqlite3.Connection) -> Dict[str, Any]:
    init_runtime_guard(conn)

    config = get_config_map(conn)

    whitelist = conn.execute(
        """
        SELECT *
        FROM v155_security_ip_whitelist
        ORDER BY created_at DESC
        """
    ).fetchall()

    quota_rows = conn.execute(
        """
        SELECT
            ip,
            COUNT(*) AS search_count,
            MAX(created_at) AS last_seen
        FROM v155_security_search_quota
        WHERE created_at >= datetime('now', 'localtime', '-24 hours')
        GROUP BY ip
        ORDER BY search_count DESC
        LIMIT 50
        """
    ).fetchall()

    block_rows = conn.execute(
        """
        SELECT *
        FROM v155_security_guard_blocks
        ORDER BY id DESC
        LIMIT 100
        """
    ).fetchall()

    search_total_24h = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM v155_security_search_quota
        WHERE created_at >= datetime('now', 'localtime', '-24 hours')
        """
    ).fetchone()["c"]

    block_total_24h = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM v155_security_guard_blocks
        WHERE created_at >= datetime('now', 'localtime', '-24 hours')
        """
    ).fetchone()["c"]

    return {
        "config": config,
        "stats": {
            "search_total_24h": int(search_total_24h or 0),
            "block_total_24h": int(block_total_24h or 0),
            "whitelist_count": len(whitelist),
            "quota_ip_count": len(quota_rows),
        },
        "whitelist": [dict(row) for row in whitelist],
        "quota_rows": [dict(row) for row in quota_rows],
        "block_rows": [dict(row) for row in block_rows],
    }


# =========================
# V15.5-S2.4 IP blocklist guard
# =========================

def init_ip_blocklist(conn: sqlite3.Connection) -> None:
    init_runtime_guard(conn)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_ip_blocklist (
            ip TEXT PRIMARY KEY,
            reason TEXT,
            source TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    # 兼容安全访问日志表不存在的情况
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            method TEXT,
            path TEXT,
            query_string TEXT,
            status_code INTEGER,
            is_suspicious INTEGER DEFAULT 0,
            suspicious_reason TEXT,
            user_agent TEXT,
            elapsed_ms REAL,
            created_at TEXT
        )
        """
    )

    conn.commit()


def is_local_or_private_ip(ip: str) -> bool:
    import ipaddress

    try:
        obj = ipaddress.ip_address(str(ip or "").strip())
        return bool(obj.is_loopback or obj.is_private or obj.is_link_local)
    except Exception:
        return False


def add_block_ip(
    conn: sqlite3.Connection,
    ip: str,
    reason: str = "",
    source: str = "manual",
) -> None:
    init_ip_blocklist(conn)

    ip = str(ip or "").strip()
    reason = str(reason or "").strip()
    source = str(source or "manual").strip()

    if not ip:
        return

    # 本机、内网、白名单不允许封禁
    if is_local_or_private_ip(ip):
        return

    if is_ip_whitelisted(conn, ip):
        return

    conn.execute(
        """
        INSERT INTO v155_security_ip_blocklist
        (ip, reason, source, is_active, created_at, updated_at)
        VALUES (?, ?, ?, 1, ?, ?)
        ON CONFLICT(ip)
        DO UPDATE SET
            reason=excluded.reason,
            source=excluded.source,
            is_active=1,
            updated_at=excluded.updated_at
        """,
        (ip, reason, source, now_str(), now_str()),
    )

    conn.commit()


def remove_block_ip(conn: sqlite3.Connection, ip: str) -> None:
    init_ip_blocklist(conn)

    ip = str(ip or "").strip()

    if not ip:
        return

    conn.execute(
        """
        UPDATE v155_security_ip_blocklist
        SET is_active=0,
            updated_at=?
        WHERE ip=?
        """,
        (now_str(), ip),
    )

    conn.commit()


def is_ip_blocked(conn: sqlite3.Connection, ip: str) -> bool:
    init_ip_blocklist(conn)

    ip = str(ip or "").strip()

    if not ip:
        return False

    if is_local_or_private_ip(ip):
        return False

    if is_ip_whitelisted(conn, ip):
        return False

    row = conn.execute(
        """
        SELECT ip
        FROM v155_security_ip_blocklist
        WHERE ip=?
          AND is_active=1
        """,
        (ip,),
    ).fetchone()

    return bool(row)


def check_ip_blocklist(
    conn: sqlite3.Connection,
    ip: str,
    method: str,
    path: str,
    query_string: str = "",
    user_agent: str = "",
):
    if not is_ip_blocked(conn, ip):
        return True, "", 200

    reason = "IP 已被加入安全封禁名单，访问被拦截"

    record_guard_block(
        conn,
        ip=ip,
        method=method,
        path=path,
        query_string=query_string,
        guard_type="ip_blocklist",
        reason=reason,
        user_agent=user_agent,
    )

    return False, reason, 403


def build_ip_blocklist_report(conn: sqlite3.Connection) -> Dict[str, Any]:
    init_ip_blocklist(conn)

    active_blocks = conn.execute(
        """
        SELECT *
        FROM v155_security_ip_blocklist
        WHERE is_active=1
        ORDER BY updated_at DESC
        """
    ).fetchall()

    inactive_blocks = conn.execute(
        """
        SELECT *
        FROM v155_security_ip_blocklist
        WHERE is_active=0
        ORDER BY updated_at DESC
        LIMIT 50
        """
    ).fetchall()

    # 最近 24 小时高风险候选：异常次数多、异常占比高
    rows = conn.execute(
        """
        SELECT
            ip,
            COUNT(*) AS total_count,
            SUM(CASE WHEN is_suspicious=1 THEN 1 ELSE 0 END) AS suspicious_count,
            MAX(created_at) AS last_seen,
            GROUP_CONCAT(DISTINCT suspicious_reason) AS reasons
        FROM v155_security_access_logs
        WHERE created_at >= datetime('now', 'localtime', '-24 hours')
          AND path NOT LIKE '/security/%'
        GROUP BY ip
        ORDER BY suspicious_count DESC, total_count DESC
        LIMIT 100
        """
    ).fetchall()

    candidates = []

    for row in rows:
        item = dict(row)
        ip = item.get("ip", "")

        if is_local_or_private_ip(ip):
            continue

        if is_ip_whitelisted(conn, ip):
            continue

        if is_ip_blocked(conn, ip):
            continue

        total = int(item.get("total_count") or 0)
        suspicious = int(item.get("suspicious_count") or 0)
        ratio = suspicious / total if total else 0

        if suspicious >= 30 or (total >= 20 and ratio >= 0.7):
            item["risk_label"] = "建议封禁"
            item["risk_reason"] = f"24小时访问 {total} 次，异常 {suspicious} 次，异常占比 {ratio:.1%}"
            candidates.append(item)
        elif suspicious >= 10 or (total >= 10 and ratio >= 0.5):
            item["risk_label"] = "建议观察"
            item["risk_reason"] = f"24小时访问 {total} 次，异常 {suspicious} 次，异常占比 {ratio:.1%}"
            candidates.append(item)

    return {
        "active_blocks": [dict(row) for row in active_blocks],
        "inactive_blocks": [dict(row) for row in inactive_blocks],
        "candidates": candidates[:50],
        "stats": {
            "active_count": len(active_blocks),
            "inactive_count": len(inactive_blocks),
            "candidate_count": len(candidates),
        },
    }
