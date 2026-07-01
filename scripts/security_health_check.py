from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path("/home/admin/ai-tool")
DB_PATH = ROOT / "data" / "snapshots.db"
TOKEN_PATH = ROOT / "data" / "security_admin_token.txt"
APP_PATH = ROOT / "app.py"
NGINX_BLOCKLIST = Path("/etc/nginx/snippets/ai-tool-ip-blocklist.conf")


REQUIRED_TABLES = [
    "v155_security_access_logs",
    "v155_security_ip_blocklist",
    "v155_security_ip_whitelist",
    "v155_security_guard_blocks",
    "v155_security_runtime_config",
    "v155_security_admin_audit_logs",
]

REQUIRED_TEMPLATES = [
    "templates/security_console.html",
    "templates/security_logs.html",
    "templates/security_blocks.html",
    "templates/security_cleanup.html",
    "templates/security_ip_detail.html",
    "templates/security_login.html",
    "templates/security_audit.html",
    "templates/security_nginx_sync.html",
]

REQUIRED_ROUTES = [
    '@app.route("/security")',
    '@app.route("/security/logs")',
    '@app.route("/security/login"',
    '@app.route("/security/logout")',
    '@app.route("/security/ip")',
    '@app.route("/security/blocks"',
    '@app.route("/security/cleanup"',
    '@app.route("/security/guard"',
    '@app.route("/security/audit")',
    '@app.route("/security/nginx"',
]


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def warn(msg: str) -> None:
    print(f"⚠️  {msg}")


def fail(msg: str) -> None:
    print(f"❌ {msg}")


def count_nginx_deny() -> int:
    if not NGINX_BLOCKLIST.exists():
        return -1

    count = 0
    for line in NGINX_BLOCKLIST.read_text(errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("deny ") and line.endswith(";"):
            count += 1
        elif line.startswith("deny ") and ";" in line:
            count += 1

    return count


def main() -> int:
    print("V15.5 Security Health Check")
    print("=" * 40)

    errors = 0

    if TOKEN_PATH.exists() and TOKEN_PATH.read_text(errors="ignore").strip():
        ok("安全后台 token 文件存在，且非空")
    else:
        fail("安全后台 token 文件缺失或为空：data/security_admin_token.txt")
        errors += 1

    if DB_PATH.exists():
        ok("数据库文件存在")
    else:
        fail("数据库文件不存在：data/snapshots.db")
        return 1

    if APP_PATH.exists():
        app_text = APP_PATH.read_text(errors="ignore")
        ok("app.py 存在")
    else:
        fail("app.py 不存在")
        return 1

    for route in REQUIRED_ROUTES:
        if route in app_text:
            ok(f"路由存在：{route}")
        else:
            fail(f"路由缺失：{route}")
            errors += 1

    for tpl in REQUIRED_TEMPLATES:
        if (ROOT / tpl).exists():
            ok(f"模板存在：{tpl}")
        else:
            fail(f"模板缺失：{tpl}")
            errors += 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    existing_tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    for table in REQUIRED_TABLES:
        if table in existing_tables:
            ok(f"数据表存在：{table}")
        else:
            fail(f"数据表缺失：{table}")
            errors += 1

    active_blocks = 0
    try:
        active_blocks = conn.execute(
            """
            SELECT COUNT(*)
            FROM v155_security_ip_blocklist
            WHERE is_active=1
            """
        ).fetchone()[0] or 0
        ok(f"数据库生效封禁 IP：{active_blocks}")
    except Exception as e:
        fail(f"读取数据库封禁名单失败：{e}")
        errors += 1

    audit_total = 0
    try:
        audit_total = conn.execute(
            """
            SELECT COUNT(*)
            FROM v155_security_admin_audit_logs
            """
        ).fetchone()[0] or 0
        ok(f"安全操作审计记录：{audit_total}")
    except Exception as e:
        fail(f"读取审计日志失败：{e}")
        errors += 1

    conn.close()

    nginx_deny = count_nginx_deny()

    if nginx_deny >= 0:
        ok(f"Nginx deny 数：{nginx_deny}")
    else:
        fail("Nginx 封禁配置文件不存在：/etc/nginx/snippets/ai-tool-ip-blocklist.conf")
        errors += 1

    if nginx_deny >= 0:
        if nginx_deny == active_blocks:
            ok("Nginx deny 与数据库封禁数量一致")
        else:
            warn(
                f"Nginx deny 与数据库封禁数量不一致：数据库={active_blocks}，Nginx={nginx_deny}。建议进入 /security/nginx 同步。"
            )

    print("=" * 40)

    if errors:
        fail(f"体检完成：发现 {errors} 个严重问题")
        return 1

    ok("体检完成：安全模块基础状态正常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
