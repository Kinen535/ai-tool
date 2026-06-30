from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Tuple


SUSPICIOUS_UA_KEYWORDS = [
    "python-requests",
    "scrapy",
    "curl",
    "wget",
    "httpclient",
    "go-http-client",
    "libwww-perl",
    "aiohttp",
    "okhttp",
    "java/",
]


def init_security_tables(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT DEFAULT '',
            method TEXT DEFAULT '',
            path TEXT DEFAULT '',
            query_string TEXT DEFAULT '',
            user_agent TEXT DEFAULT '',
            status_code INTEGER DEFAULT 0,
            duration_ms REAL DEFAULT 0,
            is_suspicious INTEGER DEFAULT 0,
            suspicious_reason TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_v155_security_access_logs_ip_time
        ON v155_security_access_logs(ip, created_at)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_v155_security_access_logs_path_time
        ON v155_security_access_logs(path, created_at)
        """
    )

    conn.commit()


def cleanup_security_logs(conn: sqlite3.Connection, keep_days: int = 7) -> None:
    init_security_tables(conn)

    conn.execute(
        """
        DELETE FROM v155_security_access_logs
        WHERE created_at < datetime('now', 'localtime', ?)
        """,
        (f"-{keep_days} days",),
    )

    conn.commit()


def is_static_path(path: str) -> bool:
    path = str(path or "")

    return (
        path.startswith("/static/")
        or path.startswith("/favicon")
        or path.endswith(".css")
        or path.endswith(".js")
        or path.endswith(".png")
        or path.endswith(".jpg")
        or path.endswith(".jpeg")
        or path.endswith(".gif")
        or path.endswith(".ico")
        or path.endswith(".svg")
    )


def get_client_ip(headers: Dict[str, Any], remote_addr: str = "") -> str:
    xff = str(headers.get("X-Forwarded-For") or "").strip()

    if xff:
        return xff.split(",")[0].strip()

    real_ip = str(headers.get("X-Real-IP") or "").strip()

    if real_ip:
        return real_ip

    return str(remote_addr or "").strip()


def detect_suspicious(
    conn: sqlite3.Connection,
    ip: str,
    method: str,
    path: str,
    query_string: str,
    user_agent: str,
    status_code: int,
) -> Tuple[bool, str]:
    init_security_tables(conn)

    reasons: List[str] = []

    ua = str(user_agent or "").lower()
    method = str(method or "").upper()
    path = str(path or "")

    if not ua:
        reasons.append("空UA")

    for keyword in SUSPICIOUS_UA_KEYWORDS:
        if keyword in ua:
            reasons.append(f"脚本UA:{keyword}")
            break

    if int(status_code or 0) in (401, 403, 404, 429):
        reasons.append(f"异常状态码:{status_code}")

    cur = conn.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(CASE WHEN path LIKE '/archives/search%' THEN 1 ELSE 0 END) AS search_count,
            SUM(CASE WHEN method='POST' THEN 1 ELSE 0 END) AS post_count,
            COUNT(DISTINCT path) AS unique_path_count,
            SUM(CASE WHEN status_code=404 THEN 1 ELSE 0 END) AS not_found_count
        FROM v155_security_access_logs
        WHERE ip = ?
          AND created_at >= datetime('now', 'localtime', '-60 seconds')
        """,
        (ip,),
    )

    row = cur.fetchone()

    if row:
        total_count = int(row["total_count"] or 0)
        search_count = int(row["search_count"] or 0)
        post_count = int(row["post_count"] or 0)
        unique_path_count = int(row["unique_path_count"] or 0)
        not_found_count = int(row["not_found_count"] or 0)

        if total_count >= 120:
            reasons.append(f"一分钟高频访问:{total_count}")

        if search_count >= 20:
            reasons.append(f"一分钟高频搜索:{search_count}")

        if post_count >= 10:
            reasons.append(f"一分钟高频提交:{post_count}")

        if unique_path_count >= 50:
            reasons.append(f"一分钟大量路径探测:{unique_path_count}")

        if not_found_count >= 20:
            reasons.append(f"一分钟大量404:{not_found_count}")

    is_suspicious = bool(reasons)

    return is_suspicious, "；".join(reasons)


def save_access_log(
    conn: sqlite3.Connection,
    ip: str,
    method: str,
    path: str,
    query_string: str,
    user_agent: str,
    status_code: int,
    duration_ms: float,
    is_suspicious: bool,
    suspicious_reason: str,
) -> None:
    init_security_tables(conn)

    conn.execute(
        """
        INSERT INTO v155_security_access_logs (
            ip,
            method,
            path,
            query_string,
            user_agent,
            status_code,
            duration_ms,
            is_suspicious,
            suspicious_reason,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """,
        (
            str(ip or ""),
            str(method or ""),
            str(path or ""),
            str(query_string or ""),
            str(user_agent or "")[:500],
            int(status_code or 0),
            float(duration_ms or 0),
            1 if is_suspicious else 0,
            str(suspicious_reason or "")[:500],
        ),
    )

    conn.commit()


def get_security_report(conn: sqlite3.Connection, limit: int = 200) -> Dict[str, Any]:
    init_security_tables(conn)

    total_24h = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM v155_security_access_logs
        WHERE created_at >= datetime('now', 'localtime', '-24 hours')
        """
    ).fetchone()["c"]

    suspicious_24h = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM v155_security_access_logs
        WHERE is_suspicious=1
          AND created_at >= datetime('now', 'localtime', '-24 hours')
        """
    ).fetchone()["c"]

    search_24h = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM v155_security_access_logs
        WHERE path LIKE '/archives/search%'
          AND created_at >= datetime('now', 'localtime', '-24 hours')
        """
    ).fetchone()["c"]

    post_24h = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM v155_security_access_logs
        WHERE method='POST'
          AND created_at >= datetime('now', 'localtime', '-24 hours')
        """
    ).fetchone()["c"]

    top_ips_cur = conn.execute(
        """
        SELECT
            ip,
            COUNT(*) AS total_count,
            SUM(CASE WHEN is_suspicious=1 THEN 1 ELSE 0 END) AS suspicious_count,
            MAX(created_at) AS last_seen
        FROM v155_security_access_logs
        WHERE created_at >= datetime('now', 'localtime', '-24 hours')
        GROUP BY ip
        ORDER BY total_count DESC
        LIMIT 20
        """
    )

    recent_cur = conn.execute(
        """
        SELECT *
        FROM v155_security_access_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )

    suspicious_cur = conn.execute(
        """
        SELECT *
        FROM v155_security_access_logs
        WHERE is_suspicious=1
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )

    return {
        "stats": {
            "total_24h": int(total_24h or 0),
            "suspicious_24h": int(suspicious_24h or 0),
            "search_24h": int(search_24h or 0),
            "post_24h": int(post_24h or 0),
        },
        "top_ips": [dict(row) for row in top_ips_cur.fetchall()],
        "recent_logs": [dict(row) for row in recent_cur.fetchall()],
        "suspicious_logs": [dict(row) for row in suspicious_cur.fetchall()],
    }
