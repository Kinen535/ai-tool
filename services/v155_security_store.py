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


def is_local_test_ip(ip: str) -> bool:
    ip = str(ip or "").strip()

    return ip in {
        "127.0.0.1",
        "::1",
        "localhost",
    }


def classify_ip_risk(total_count: int, suspicious_count: int, last_seen: str = "") -> Dict[str, Any]:
    total_count = int(total_count or 0)
    suspicious_count = int(suspicious_count or 0)

    ratio = 0.0

    if total_count > 0:
        ratio = round(suspicious_count / total_count * 100, 1)

    if suspicious_count >= 50 or (total_count >= 30 and ratio >= 60):
        return {
            "risk_level": "high",
            "risk_label": "高风险",
            "risk_reason": f"异常次数 {suspicious_count}，异常占比 {ratio}%",
            "risk_score": min(100, suspicious_count + int(ratio)),
            "suspicious_ratio": ratio,
        }

    if suspicious_count >= 10 or (total_count >= 15 and ratio >= 30):
        return {
            "risk_level": "watch",
            "risk_label": "观察",
            "risk_reason": f"存在异常访问，异常占比 {ratio}%",
            "risk_score": min(80, suspicious_count + int(ratio / 2)),
            "suspicious_ratio": ratio,
        }

    if suspicious_count > 0:
        return {
            "risk_level": "notice",
            "risk_label": "轻微异常",
            "risk_reason": f"少量异常访问，异常占比 {ratio}%",
            "risk_score": min(50, suspicious_count + int(ratio / 3)),
            "suspicious_ratio": ratio,
        }

    return {
        "risk_level": "normal",
        "risk_label": "正常",
        "risk_reason": "暂无明显异常",
        "risk_score": 0,
        "suspicious_ratio": ratio,
    }




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

    real_suspicious_24h = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM v155_security_access_logs
        WHERE is_suspicious=1
          AND ip NOT IN ('127.0.0.1', '::1', 'localhost')
          AND created_at >= datetime('now', 'localtime', '-24 hours')
        """
    ).fetchone()["c"]

    local_test_suspicious_24h = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM v155_security_access_logs
        WHERE is_suspicious=1
          AND ip IN ('127.0.0.1', '::1', 'localhost')
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
        LIMIT 30
        """
    )

    top_ips = []

    high_risk_count = 0
    watch_count = 0
    local_test_count = 0

    for row in top_ips_cur.fetchall():
        item = dict(row)

        item["is_local_test"] = 1 if is_local_test_ip(item.get("ip")) else 0

        risk = classify_ip_risk(
            item.get("total_count", 0),
            item.get("suspicious_count", 0),
            item.get("last_seen", ""),
        )

        if item["is_local_test"]:
            risk["risk_level"] = "local"
            risk["risk_label"] = "本机测试"
            risk["risk_reason"] = "服务器本机 curl / 自测访问"
            local_test_count += 1
        elif risk["risk_level"] == "high":
            high_risk_count += 1
        elif risk["risk_level"] in ("watch", "notice"):
            watch_count += 1

        item.update(risk)
        top_ips.append(item)

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

    real_suspicious_cur = conn.execute(
        """
        SELECT *
        FROM v155_security_access_logs
        WHERE is_suspicious=1
          AND ip NOT IN ('127.0.0.1', '::1', 'localhost')
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )

    return {
        "stats": {
            "total_24h": int(total_24h or 0),
            "suspicious_24h": int(suspicious_24h or 0),
            "real_suspicious_24h": int(real_suspicious_24h or 0),
            "local_test_suspicious_24h": int(local_test_suspicious_24h or 0),
            "search_24h": int(search_24h or 0),
            "post_24h": int(post_24h or 0),
            "high_risk_ip_count": int(high_risk_count or 0),
            "watch_ip_count": int(watch_count or 0),
            "local_test_ip_count": int(local_test_count or 0),
        },
        "top_ips": top_ips,
        "recent_logs": [dict(row) for row in recent_cur.fetchall()],
        "suspicious_logs": [dict(row) for row in suspicious_cur.fetchall()],
        "real_suspicious_logs": [dict(row) for row in real_suspicious_cur.fetchall()],
    }


def get_ip_detail_report(conn: sqlite3.Connection, ip: str, limit: int = 300) -> Dict[str, Any]:
    init_security_tables(conn)

    ip = str(ip or "").strip()

    summary = conn.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(CASE WHEN is_suspicious=1 THEN 1 ELSE 0 END) AS suspicious_count,
            SUM(CASE WHEN path LIKE '/archives/search%' THEN 1 ELSE 0 END) AS search_count,
            SUM(CASE WHEN method='POST' THEN 1 ELSE 0 END) AS post_count,
            SUM(CASE WHEN status_code=404 THEN 1 ELSE 0 END) AS not_found_count,
            MIN(created_at) AS first_seen,
            MAX(created_at) AS last_seen
        FROM v155_security_access_logs
        WHERE ip = ?
          AND created_at >= datetime('now', 'localtime', '-24 hours')
        """,
        (ip,),
    ).fetchone()

    total_count = int(summary["total_count"] or 0)
    suspicious_count = int(summary["suspicious_count"] or 0)

    risk = classify_ip_risk(
        total_count,
        suspicious_count,
        summary["last_seen"] if summary else "",
    )

    if is_local_test_ip(ip):
        risk["risk_level"] = "local"
        risk["risk_label"] = "本机测试"
        risk["risk_reason"] = "服务器本机 curl / 自测访问"

    paths_cur = conn.execute(
        """
        SELECT
            path,
            COUNT(*) AS total_count,
            SUM(CASE WHEN is_suspicious=1 THEN 1 ELSE 0 END) AS suspicious_count,
            MAX(created_at) AS last_seen
        FROM v155_security_access_logs
        WHERE ip = ?
          AND created_at >= datetime('now', 'localtime', '-24 hours')
        GROUP BY path
        ORDER BY total_count DESC
        LIMIT 50
        """,
        (ip,),
    )

    ua_cur = conn.execute(
        """
        SELECT
            user_agent,
            COUNT(*) AS total_count,
            MAX(created_at) AS last_seen
        FROM v155_security_access_logs
        WHERE ip = ?
          AND created_at >= datetime('now', 'localtime', '-24 hours')
        GROUP BY user_agent
        ORDER BY total_count DESC
        LIMIT 20
        """,
        (ip,),
    )

    logs_cur = conn.execute(
        """
        SELECT *
        FROM v155_security_access_logs
        WHERE ip = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (ip, limit),
    )

    return {
        "ip": ip,
        "summary": {
            "total_count": total_count,
            "suspicious_count": suspicious_count,
            "search_count": int(summary["search_count"] or 0),
            "post_count": int(summary["post_count"] or 0),
            "not_found_count": int(summary["not_found_count"] or 0),
            "first_seen": summary["first_seen"] or "",
            "last_seen": summary["last_seen"] or "",
            "is_local_test": 1 if is_local_test_ip(ip) else 0,
        },
        "risk": risk,
        "paths": [dict(row) for row in paths_cur.fetchall()],
        "user_agents": [dict(row) for row in ua_cur.fetchall()],
        "logs": [dict(row) for row in logs_cur.fetchall()],
    }


# =========================
# V15.5-S2.1 security logs pagination
# =========================

def get_security_report_paginated(
    conn: sqlite3.Connection,
    page: int = 1,
    per_page: int = 30,
) -> Dict[str, Any]:
    init_security_tables(conn)

    try:
        page = int(page or 1)
    except Exception:
        page = 1

    try:
        per_page = int(per_page or 30)
    except Exception:
        per_page = 30

    if page < 1:
        page = 1

    if per_page < 1:
        per_page = 30

    if per_page > 100:
        per_page = 100

    offset = (page - 1) * per_page

    # 先复用原安全报表，只把明细限制到每页数量，避免页面过长
    report = get_security_report(conn, limit=per_page)

    grouped_rows = conn.execute(
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
        """
    ).fetchall()

    total_ips = len(grouped_rows)
    total_pages = max(1, (total_ips + per_page - 1) // per_page)

    if page > total_pages:
        page = total_pages
        offset = (page - 1) * per_page

    high_risk_count = 0
    watch_count = 0
    local_test_count = 0

    all_items = []

    for row in grouped_rows:
        item = dict(row)

        item["is_local_test"] = 1 if is_local_test_ip(item.get("ip")) else 0

        risk = classify_ip_risk(
            item.get("total_count", 0),
            item.get("suspicious_count", 0),
            item.get("last_seen", ""),
        )

        if item["is_local_test"]:
            risk["risk_level"] = "local"
            risk["risk_label"] = "本机测试"
            risk["risk_reason"] = "服务器本机 curl / 自测访问"
            local_test_count += 1
        elif risk["risk_level"] == "high":
            high_risk_count += 1
        elif risk["risk_level"] in ("watch", "notice"):
            watch_count += 1

        item.update(risk)
        all_items.append(item)

    report["top_ips"] = all_items[offset:offset + per_page]

    report["stats"]["high_risk_ip_count"] = high_risk_count
    report["stats"]["watch_ip_count"] = watch_count
    report["stats"]["local_test_ip_count"] = local_test_count

    report["pagination"] = {
        "page": page,
        "per_page": per_page,
        "top_ip_total": total_ips,
        "top_ip_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": max(1, page - 1),
        "next_page": min(total_pages, page + 1),
    }

    return report
