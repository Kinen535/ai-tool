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


def _cleanup_security_logs_by_days(conn: sqlite3.Connection, keep_days: int = 7) -> None:
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
    path_lower = path.lower()

    # ------------------------------------------------------------
    # Strong path-based scanner evidence.
    #
    # Keep this deliberately narrow. These are application-
    # irrelevant exploit / credential probes seen in real traffic.
    # Do not treat /.well-known/* as suspicious generically because
    # passkey-endpoints is legitimate platform discovery traffic.
    # ------------------------------------------------------------

    if (
        path_lower == "/xmlrpc.php"
        or path_lower == "/wp-admin/install.php"
        or path_lower.startswith(
            "/wp-json/wp/v2/users"
        )
        or path_lower.endswith(
            "/wp-login.php"
        )
    ):
        reasons.append(
            "扫描路径:WordPress探测"
        )

    elif (
        "/vendor/phpunit/"
        in path_lower
        and path_lower.endswith(
            "/eval-stdin.php"
        )
    ):
        reasons.append(
            "扫描路径:PHPUnit漏洞探测"
        )

    elif (
        path_lower
        in {
            "/env",
            "/.env",
            "/env.example",
            "/.env.example",
            "/config.env",
            "/config.json",
            "/config/app.php",
            "/.bashrc",
            "/deploy.sh",
        }
        or path_lower.startswith(
            "/.aws/"
        )
        or path_lower.startswith(
            "/.git/"
        )
        or path_lower.endswith(
            "/.env"
        )
        or path_lower.endswith(
            "/.bashrc"
        )
        or path_lower.endswith(
            "/deploy.sh"
        )
        or path_lower.rsplit(
            "/",
            1,
        )[-1]
        in {
            "phpinfo.php",
            "phpinfo.php3",
            "php-info.php",
        }
    ):
        reasons.append(
            "扫描路径:敏感文件探测"
        )

    elif (
        path_lower.startswith(
            "/web-inf/"
        )
        or "/web-inf/"
        in path_lower
    ):
        reasons.append(
            "扫描路径:WEB-INF探测"
        )

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
          AND path NOT LIKE '/security/%'
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

def get_security_identity_attribution(
    conn: sqlite3.Connection,
    ip: str,
    *,
    user_agent: str = "",
    observed_at: str = "",
) -> Dict[str, Any]:
    """
    Resolve security traffic to known application identities
    without mutating the security access log.

    Confidence semantics:
      high:
        exactly one user has a time-overlapping session and
        user-agent also matches when UA evidence is available.

      medium:
        exactly one user has a time-overlapping session, but
        user-agent evidence is absent or not exact.

      ambiguous:
        more than one user is supported by overlapping session
        evidence for the same public IP.

      historical:
        no overlapping session is found, but login history
        proves prior use of this IP.

      unattributed:
        no reliable application identity evidence exists.
    """
    ip = str(ip or "").strip()
    user_agent = str(user_agent or "").strip()
    observed_at = str(observed_at or "").strip()

    empty = {
        "confidence": "unattributed",
        "confidence_label": "未归因",
        "user_id": None,
        "username": "",
        "display_name": "",
        "role": "",
        "user_status": "",
        "candidate_count": 0,
        "candidate_users": [],
        "session_id": None,
        "session_status": "",
        "session_created_at": "",
        "session_last_seen_at": "",
        "session_expires_at": "",
        "device_label": "",
        "evidence": "无可靠账号证据",
    }

    if not ip:
        return empty

    if not observed_at:
        observed_at = (
            conn.execute(
                """
                SELECT MAX(created_at)
                FROM v155_security_access_logs
                WHERE ip=?
                """,
                (ip,),
            ).fetchone()[0]
            or ""
        )

    session_rows = conn.execute(
        """
        SELECT
            s.id AS session_id,
            s.user_id,
            s.status AS session_status,
            s.created_at AS session_created_at,
            s.last_seen_at AS session_last_seen_at,
            s.expires_at AS session_expires_at,
            s.revoked_at,
            s.login_ip,
            s.last_ip,
            s.user_agent AS session_user_agent,
            s.device_label,
            u.username,
            u.display_name,
            u.role,
            u.status AS user_status
        FROM v155_user_sessions s
        JOIN v158_users u
          ON u.id = s.user_id
        WHERE
            s.login_ip = ?
            OR s.last_ip = ?
        ORDER BY
            CASE
                WHEN s.status='active' THEN 0
                ELSE 1
            END,
            s.created_at DESC,
            s.id DESC
        """,
        (
            ip,
            ip,
        ),
    ).fetchall()

    # Security access logs use server-local naive timestamps
    # such as:
    #     2026-10-08 10:26:40
    #
    # Session registry timestamps use UTC ISO timestamps
    # such as:
    #     2026-10-08T01:19:04Z
    #
    # They must never be compared lexicographically.
    from datetime import datetime, timezone

    local_tz = (
        datetime.now()
        .astimezone()
        .tzinfo
    )

    def parse_identity_time(
        value,
        *,
        naive_timezone,
    ):
        value = str(
            value or ""
        ).strip()

        if not value:
            return None

        normalized = value

        if normalized.endswith("Z"):
            normalized = (
                normalized[:-1]
                + "+00:00"
            )

        try:
            result = (
                datetime.fromisoformat(
                    normalized
                )
            )
        except ValueError:
            return None

        if result.tzinfo is None:
            result = result.replace(
                tzinfo=naive_timezone
            )

        return result.astimezone(
            timezone.utc
        )

    observed_dt = (
        parse_identity_time(
            observed_at,
            naive_timezone=local_tz,
        )
        if observed_at
        else None
    )

    candidate_users = {}

    for row in session_rows:
        item = dict(row)

        include = True

        if observed_dt is not None:
            started_at = (
                parse_identity_time(
                    item.get(
                        "session_created_at"
                    ),
                    naive_timezone=timezone.utc,
                )
            )

            ended_raw = (
                item.get("revoked_at")
                or item.get(
                    "session_expires_at"
                )
            )

            ended_at = (
                parse_identity_time(
                    ended_raw,
                    naive_timezone=timezone.utc,
                )
            )

            if (
                started_at is None
                or observed_dt < started_at
            ):
                include = False

            if (
                include
                and ended_at is not None
                and observed_dt > ended_at
            ):
                include = False

        if not include:
            continue

        uid = int(
            item["user_id"]
        )

        if uid not in candidate_users:
            candidate_users[uid] = item

    candidates = list(
        candidate_users.values()
    )

    if len(candidates) > 1:
        labels = []

        for item in candidates:
            name = (
                str(
                    item.get("display_name")
                    or item.get("username")
                    or item.get("user_id")
                )
            )
            labels.append(name)

        result = dict(empty)
        result.update(
            {
                "confidence": "ambiguous",
                "confidence_label": "多账号共享IP",
                "candidate_count": len(candidates),
                "candidate_users": [
                    {
                        "user_id": int(
                            item["user_id"]
                        ),
                        "username": str(
                            item.get("username")
                            or ""
                        ),
                        "display_name": str(
                            item.get("display_name")
                            or ""
                        ),
                        "role": str(
                            item.get("role")
                            or ""
                        ),
                    }
                    for item in candidates
                ],
                "evidence": (
                    "同一时间窗口内该公网IP存在多个账号候选："
                    + "、".join(labels)
                ),
            }
        )

        return result

    if len(candidates) == 1:
        item = candidates[0]

        session_ua = str(
            item.get("session_user_agent")
            or ""
        ).strip()

        ua_exact = bool(
            user_agent
            and session_ua
            and user_agent == session_ua
        )

        confidence = (
            "high"
            if ua_exact
            else "medium"
        )

        confidence_label = (
            "高可信账号"
            if ua_exact
            else "会话关联"
        )

        evidence = (
            "IP、访问时间与登录会话重合"
        )

        if ua_exact:
            evidence += "，且User-Agent一致"
        elif user_agent and session_ua:
            evidence += "，但User-Agent不完全一致"
        else:
            evidence += "，User-Agent证据不足"

        result = dict(empty)
        result.update(
            {
                "confidence": confidence,
                "confidence_label": confidence_label,
                "user_id": int(
                    item["user_id"]
                ),
                "username": str(
                    item.get("username")
                    or ""
                ),
                "display_name": str(
                    item.get("display_name")
                    or ""
                ),
                "role": str(
                    item.get("role")
                    or ""
                ),
                "user_status": str(
                    item.get("user_status")
                    or ""
                ),
                "candidate_count": 1,
                "candidate_users": [
                    {
                        "user_id": int(
                            item["user_id"]
                        ),
                        "username": str(
                            item.get("username")
                            or ""
                        ),
                        "display_name": str(
                            item.get("display_name")
                            or ""
                        ),
                        "role": str(
                            item.get("role")
                            or ""
                        ),
                    }
                ],
                "session_id": int(
                    item["session_id"]
                ),
                "session_status": str(
                    item.get(
                        "session_status"
                    )
                    or ""
                ),
                "session_created_at": str(
                    item.get(
                        "session_created_at"
                    )
                    or ""
                ),
                "session_last_seen_at": str(
                    item.get(
                        "session_last_seen_at"
                    )
                    or ""
                ),
                "session_expires_at": str(
                    item.get(
                        "session_expires_at"
                    )
                    or ""
                ),
                "device_label": str(
                    item.get("device_label")
                    or ""
                ),
                "evidence": evidence,
            }
        )

        return result

    historical_rows = conn.execute(
        """
        SELECT
            l.user_id,
            l.username_snapshot,
            MAX(l.created_at) AS last_login_seen,
            u.display_name,
            u.role,
            u.status AS user_status
        FROM v158_login_logs l
        LEFT JOIN v158_users u
          ON u.id = l.user_id
        WHERE l.ip_address=?
          AND l.user_id IS NOT NULL
        GROUP BY
            l.user_id,
            l.username_snapshot,
            u.display_name,
            u.role,
            u.status
        ORDER BY last_login_seen DESC
        """,
        (ip,),
    ).fetchall()

    historical_users = {}

    for row in historical_rows:
        item = dict(row)
        uid = int(item["user_id"])

        if uid not in historical_users:
            historical_users[uid] = item

    history = list(
        historical_users.values()
    )

    if len(history) == 1:
        item = history[0]

        result = dict(empty)
        result.update(
            {
                "confidence": "historical",
                "confidence_label": "历史登录关联",
                "user_id": int(
                    item["user_id"]
                ),
                "username": str(
                    item.get(
                        "username_snapshot"
                    )
                    or ""
                ),
                "display_name": str(
                    item.get("display_name")
                    or ""
                ),
                "role": str(
                    item.get("role")
                    or ""
                ),
                "user_status": str(
                    item.get("user_status")
                    or ""
                ),
                "candidate_count": 1,
                "candidate_users": [
                    {
                        "user_id": int(
                            item["user_id"]
                        ),
                        "username": str(
                            item.get(
                                "username_snapshot"
                            )
                            or ""
                        ),
                        "display_name": str(
                            item.get(
                                "display_name"
                            )
                            or ""
                        ),
                        "role": str(
                            item.get("role")
                            or ""
                        ),
                    }
                ],
                "evidence": (
                    "该IP存在单一账号历史登录记录；"
                    "当前访问未命中明确会话时间窗口"
                ),
            }
        )

        return result

    if len(history) > 1:
        result = dict(empty)
        result.update(
            {
                "confidence": "ambiguous",
                "confidence_label": "多账号历史共享IP",
                "candidate_count": len(history),
                "candidate_users": [
                    {
                        "user_id": int(
                            item["user_id"]
                        ),
                        "username": str(
                            item.get(
                                "username_snapshot"
                            )
                            or ""
                        ),
                        "display_name": str(
                            item.get(
                                "display_name"
                            )
                            or ""
                        ),
                        "role": str(
                            item.get("role")
                            or ""
                        ),
                    }
                    for item in history
                ],
                "evidence": (
                    "该IP存在多个账号历史登录记录，"
                    "不能安全归属给单一用户"
                ),
            }
        )

        return result

    return empty



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
    report = get_security_report(conn, limit=20)

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

        attribution = (
            get_security_identity_attribution(
                conn,
                item.get("ip", ""),
                observed_at=item.get(
                    "last_seen",
                    "",
                ),
            )
        )

        item["identity"] = attribution

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


# =========================
# V15.5-S2.3 security log cleanup
# =========================

def ensure_security_cleanup_tables(conn: sqlite3.Connection) -> None:
    init_security_tables(conn)

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

    conn.commit()


def build_security_cleanup_report(conn: sqlite3.Connection) -> Dict[str, Any]:
    ensure_security_cleanup_tables(conn)

    def one(sql: str) -> int:
        row = conn.execute(sql).fetchone()
        return int(row[0] or 0)

    return {
        "counts": {
            "access_total": one("SELECT COUNT(*) FROM v155_security_access_logs"),
            "access_older_7d": one(
                """
                SELECT COUNT(*)
                FROM v155_security_access_logs
                WHERE created_at < datetime('now', 'localtime', '-7 days')
                """
            ),
            "local_test_total": one(
                """
                SELECT COUNT(*)
                FROM v155_security_access_logs
                WHERE ip IN ('127.0.0.1', '::1')
                """
            ),
            "suspicious_total": one(
                """
                SELECT COUNT(*)
                FROM v155_security_access_logs
                WHERE is_suspicious=1
                """
            ),
            "guard_block_total": one("SELECT COUNT(*) FROM v155_security_guard_blocks"),
            "guard_block_older_30d": one(
                """
                SELECT COUNT(*)
                FROM v155_security_guard_blocks
                WHERE created_at < datetime('now', 'localtime', '-30 days')
                """
            ),
            "quota_total": one("SELECT COUNT(*) FROM v155_security_search_quota"),
            "quota_older_3d": one(
                """
                SELECT COUNT(*)
                FROM v155_security_search_quota
                WHERE created_at < datetime('now', 'localtime', '-3 days')
                """
            ),
        }
    }


def _cleanup_security_logs_by_action(conn: sqlite3.Connection, action: str) -> Dict[str, Any]:
    ensure_security_cleanup_tables(conn)

    action = str(action or "").strip()

    before = build_security_cleanup_report(conn)["counts"]

    if action == "clear_local_test":
        conn.execute(
            """
            DELETE FROM v155_security_access_logs
            WHERE ip IN ('127.0.0.1', '::1')
            """
        )
        message = "已清理本机测试访问日志。"

    elif action == "clear_access_older_7d":
        conn.execute(
            """
            DELETE FROM v155_security_access_logs
            WHERE created_at < datetime('now', 'localtime', '-7 days')
            """
        )
        message = "已清理 7 天前访问日志。"

    elif action == "clear_guard_older_30d":
        conn.execute(
            """
            DELETE FROM v155_security_guard_blocks
            WHERE created_at < datetime('now', 'localtime', '-30 days')
            """
        )
        message = "已清理 30 天前安全闸门拦截日志。"

    elif action == "clear_quota_older_3d":
        conn.execute(
            """
            DELETE FROM v155_security_search_quota
            WHERE created_at < datetime('now', 'localtime', '-3 days')
            """
        )
        message = "已清理 3 天前搜索额度记录。"

    elif action == "vacuum":
        conn.commit()
        conn.execute("VACUUM")
        message = "已执行 SQLite VACUUM 压缩。"

    else:
        return {
            "ok": False,
            "message": "未知清理动作，未执行。",
            "before": before,
            "after": before,
        }

    conn.commit()

    after = build_security_cleanup_report(conn)["counts"]

    return {
        "ok": True,
        "message": message,
        "before": before,
        "after": after,
    }


# =========================
# V15.5-S2.6 enhanced IP detail report
# =========================

def get_ip_detail_report(conn: sqlite3.Connection, ip: str, limit: int = 300) -> Dict[str, Any]:
    init_security_tables(conn)

    ip = str(ip or "").strip()

    # 兼容白名单 / 封禁表不存在的情况
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_ip_whitelist (
            ip TEXT PRIMARY KEY,
            note TEXT,
            created_at TEXT
        )
        """
    )

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

    conn.commit()

    summary = conn.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(CASE WHEN is_suspicious=1 THEN 1 ELSE 0 END) AS suspicious_count,
            SUM(CASE WHEN path LIKE '/archives/search%' OR path LIKE '/archive_search%' THEN 1 ELSE 0 END) AS search_count,
            SUM(CASE WHEN method='POST' THEN 1 ELSE 0 END) AS post_count,
            SUM(CASE WHEN status_code=404 THEN 1 ELSE 0 END) AS not_found_count,
            SUM(CASE WHEN path LIKE '/security/%' THEN 1 ELSE 0 END) AS security_count,
            SUM(CASE WHEN path IN (
                '/security/logs',
                '/security/ip',
                '/security/guard',
                '/security/cleanup',
                '/security/blocks'
            ) AND status_code=200 THEN 1 ELSE 0 END) AS admin_panel_count,
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
    search_count = int(summary["search_count"] or 0)
    post_count = int(summary["post_count"] or 0)
    not_found_count = int(summary["not_found_count"] or 0)
    security_count = int(summary["security_count"] or 0)
    admin_panel_count = int(summary["admin_panel_count"] or 0)

    suspicious_ratio = 0.0
    if total_count > 0:
        suspicious_ratio = round(suspicious_count / total_count * 100, 1)

    whitelist_row = conn.execute(
        """
        SELECT *
        FROM v155_security_ip_whitelist
        WHERE ip=?
        """,
        (ip,),
    ).fetchone()

    block_row = conn.execute(
        """
        SELECT *
        FROM v155_security_ip_blocklist
        WHERE ip=?
          AND is_active=1
        """,
        (ip,),
    ).fetchone()

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

    user_agents = [dict(row) for row in ua_cur.fetchall()]

    scan_keywords = [
        "nmap",
        "zgrab",
        "curl",
        "python-requests",
        "scrapy",
        "wget",
        "go-http-client",
        "masscan",
        "libwww-perl",
        "aiohttp",
        "java/",
        "okhttp",
    ]

    scanner_hits = []

    for row in user_agents:
        ua = str(row.get("user_agent") or "").lower()
        for keyword in scan_keywords:
            if keyword in ua:
                scanner_hits.append(keyword)
                break

    scanner_hits = sorted(set(scanner_hits))

    paths_cur = conn.execute(
        """
        SELECT
            path,
            COUNT(*) AS total_count,
            SUM(CASE WHEN is_suspicious=1 THEN 1 ELSE 0 END) AS suspicious_count,
            SUM(CASE WHEN status_code=404 THEN 1 ELSE 0 END) AS not_found_count,
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

    is_whitelisted = bool(whitelist_row)
    is_blocked = bool(block_row)
    is_admin_access = admin_panel_count > 0
    is_local = is_local_test_ip(ip)

    risk = classify_ip_risk(
        total_count,
        suspicious_count,
        summary["last_seen"] if summary else "",
    )

    recommendation = {
        "action": "ignore",
        "label": "忽略",
        "level": "normal",
        "reason": "暂无明显异常。"
    }

    if is_local:
        risk["risk_level"] = "local"
        risk["risk_label"] = "本机测试"
        risk["risk_reason"] = "服务器本机 curl / 自测访问"
        recommendation = {
            "action": "ignore",
            "label": "忽略",
            "level": "local",
            "reason": "这是服务器本机测试访问，不需要处理。"
        }

    elif is_whitelisted:
        risk["risk_level"] = "whitelist"
        risk["risk_label"] = "白名单"
        risk["risk_reason"] = "该 IP 已加入白名单。"
        recommendation = {
            "action": "ignore",
            "label": "忽略",
            "level": "whitelist",
            "reason": "该 IP 已在白名单，不建议封禁。"
        }

    elif is_admin_access:
        risk["risk_level"] = "admin"
        risk["risk_label"] = "管理员访问"
        risk["risk_reason"] = "该 IP 访问过安全后台，疑似管理员当前网络。"
        recommendation = {
            "action": "ignore",
            "label": "管理员访问，暂不处理",
            "level": "admin",
            "reason": "该 IP 有安全后台访问记录，优先判断为管理员自用网络。"
        }

    elif is_blocked:
        risk["risk_level"] = "blocked"
        risk["risk_label"] = "已封禁"
        risk["risk_reason"] = block_row["reason"] if block_row else "已在封禁名单。"
        recommendation = {
            "action": "blocked",
            "label": "已封禁",
            "level": "blocked",
            "reason": "该 IP 已在生效封禁名单中。"
        }

    else:
        # V15.5-S2.6.1 推荐策略修正：
        # curl / python-requests / wget 这类弱脚本 UA 不能单独触发“建议封禁”；
        # nmap / zgrab / masscan 这类强扫描器才可以直接进入封禁建议。
        hard_scanners = {"nmap", "zgrab", "masscan"}
        soft_scripts = {
            "curl",
            "python-requests",
            "wget",
            "go-http-client",
            "scrapy",
            "aiohttp",
            "java/",
            "okhttp",
            "libwww-perl",
        }

        has_hard_scanner = any(x in hard_scanners for x in scanner_hits)
        has_soft_script = any(x in soft_scripts for x in scanner_hits)

        if (
            has_hard_scanner
            or not_found_count >= 20
            or suspicious_count >= 30
            or (has_soft_script and suspicious_count >= 10)
            or (has_soft_script and not_found_count >= 5)
        ):
            recommendation = {
                "action": "block",
                "label": "建议封禁",
                "level": "danger",
                "reason": "存在强扫描器 UA、大量 404 探测、高异常访问，或脚本 UA 伴随明显异常。"
            }

        elif (
            has_soft_script
            or suspicious_count >= 10
            or not_found_count >= 5
            or search_count >= 30
        ):
            recommendation = {
                "action": "watch",
                "label": "建议观察",
                "level": "watch",
                "reason": "存在脚本 UA 或一定异常访问，建议观察，暂不直接封禁。"
            }

        elif suspicious_count > 0:
            recommendation = {
                "action": "notice",
                "label": "轻微异常",
                "level": "notice",
                "reason": "存在少量异常记录，暂不需要处理。"
            }

    latest_log_row = conn.execute(
        """
        SELECT
            user_agent,
            created_at
        FROM v155_security_access_logs
        WHERE ip=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (ip,),
    ).fetchone()

    attribution = (
        get_security_identity_attribution(
            conn,
            ip,
            user_agent=(
                str(
                    latest_log_row[
                        "user_agent"
                    ]
                    or ""
                )
                if latest_log_row
                else ""
            ),
            observed_at=(
                str(
                    latest_log_row[
                        "created_at"
                    ]
                    or ""
                )
                if latest_log_row
                else ""
            ),
        )
    )


    return {
        "ip": ip,
        "summary": {
            "total_count": total_count,
            "suspicious_count": suspicious_count,
            "suspicious_ratio": suspicious_ratio,
            "search_count": search_count,
            "post_count": post_count,
            "not_found_count": not_found_count,
            "security_count": security_count,
            "admin_panel_count": admin_panel_count,
            "first_seen": summary["first_seen"] or "",
            "last_seen": summary["last_seen"] or "",
            "is_local_test": 1 if is_local else 0,
            "is_whitelisted": 1 if is_whitelisted else 0,
            "is_blocked": 1 if is_blocked else 0,
            "is_admin_access": 1 if is_admin_access else 0,
            "scanner_hits": scanner_hits,
        },
        "identity": attribution,
        "risk": risk,
        "recommendation": recommendation,
        "whitelist": dict(whitelist_row) if whitelist_row else None,
        "block": dict(block_row) if block_row else None,
        "paths": [dict(row) for row in paths_cur.fetchall()],
        "user_agents": user_agents,
        "logs": [dict(row) for row in logs_cur.fetchall()],
    }

# V15.5-S0B unified cleanup_security_logs wrapper
def cleanup_security_logs(conn, action=None, keep_days=7, **kwargs):
    """
    兼容两种历史调用：
    1. cleanup_security_logs(conn, keep_days=7)
    2. cleanup_security_logs(conn, action)
    """
    if action is None:
        result = _cleanup_security_logs_by_days(conn, keep_days=keep_days)
        if isinstance(result, dict):
            return result
        return {
            "ok": True,
            "action": "keep_days",
            "keep_days": keep_days,
            "message": "security logs cleanup by keep_days completed",
        }

    return _cleanup_security_logs_by_action(conn, action)

