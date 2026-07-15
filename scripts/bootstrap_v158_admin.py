#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path
from typing import Any

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "snapshots.db"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.v158_auth_store import (  # noqa: E402
    create_user,
    get_user_by_id,
    get_v158_auth_schema_status,
    normalize_username,
    record_action_log,
    validate_username,
)


def connect_database(
    db_path: Path,
) -> sqlite3.Connection:
    conn = sqlite3.connect(
        db_path,
        timeout=30,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def validate_password(
    password: str,
    *,
    username: str,
) -> None:
    if len(password) < 12:
        raise ValueError("密码长度不能少于12位。")

    if len(password) > 128:
        raise ValueError("密码长度不能超过128位。")

    if any(character.isspace() for character in password):
        raise ValueError("密码中不能包含空格或换行。")

    if username.lower() in password.lower():
        raise ValueError("密码不能包含用户名。")

    categories = [
        any(character.islower() for character in password),
        any(character.isupper() for character in password),
        any(character.isdigit() for character in password),
        any(not character.isalnum() for character in password),
    ]

    if sum(categories) < 3:
        raise ValueError(
            "密码必须至少包含以下四类中的三类："
            "大写字母、小写字母、数字、特殊字符。"
        )


def bootstrap_super_admin(
    conn: sqlite3.Connection,
    *,
    username: str,
    display_name: str,
    password: str,
) -> dict[str, Any]:
    schema_status = get_v158_auth_schema_status(conn)

    if not schema_status.get("ok"):
        raise RuntimeError(
            "V15.8认证表尚未完整迁移，禁止创建账号。"
        )

    username = normalize_username(username)
    display_name = str(display_name or "").strip()

    validate_username(username)
    validate_password(
        password,
        username=username,
    )

    if not display_name:
        display_name = username

    if len(display_name) > 100:
        raise ValueError("显示名称不能超过100个字符。")

    password_hash = generate_password_hash(
        password,
        method="scrypt",
    )

    if not check_password_hash(
        password_hash,
        password,
    ):
        raise RuntimeError("密码哈希自检失败。")

    try:
        conn.execute("BEGIN IMMEDIATE")

        total_users = int(
            conn.execute(
                "SELECT COUNT(*) FROM v158_users"
            ).fetchone()[0]
        )

        if total_users != 0:
            raise RuntimeError(
                "系统中已经存在账号，初始管理员脚本拒绝继续执行。"
            )

        user_id = create_user(
            conn,
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            role="super_admin",
            status="active",
            must_change_password=False,
        )

        record_action_log(
            conn,
            user_id=None,
            username_snapshot="system",
            role_snapshot="system",
            action_key="bootstrap_super_admin",
            action_label="创建初始超级管理员",
            target_type="user",
            target_id=str(user_id),
            target_label=username,
            result_status="success",
            after_data={
                "id": user_id,
                "username": username,
                "display_name": display_name,
                "role": "super_admin",
                "status": "active",
                "must_change_password": 0,
            },
            reason="V15.8初始认证账号引导创建",
            request_method="CLI",
            request_path="scripts/bootstrap_v158_admin.py",
        )

        conn.commit()

    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise

    user = get_user_by_id(conn, user_id)

    if not user:
        raise RuntimeError("初始管理员创建后无法读取。")

    return user


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="创建V15.8初始超级管理员",
    )

    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help="SQLite数据库路径",
    )

    parser.add_argument(
        "--username",
        help="初始管理员用户名",
    )

    parser.add_argument(
        "--display-name",
        default="",
        help="显示名称",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    db_path = Path(args.db).expanduser().resolve()

    if not db_path.is_file():
        print(
            f"数据库不存在：{db_path}",
            file=sys.stderr,
        )
        return 1

    username = args.username

    if not username:
        username = input(
            "请输入初始超级管理员用户名："
        ).strip()

    display_name = args.display_name

    if not display_name:
        display_name = input(
            "请输入显示名称，可留空："
        ).strip()

    password = getpass.getpass(
        "请输入初始管理员密码："
    )

    password_confirm = getpass.getpass(
        "请再次输入密码："
    )

    if password != password_confirm:
        print(
            "两次输入的密码不一致。",
            file=sys.stderr,
        )
        return 1

    conn = connect_database(db_path)

    try:
        user = bootstrap_super_admin(
            conn,
            username=username,
            display_name=display_name,
            password=password,
        )
    except Exception as exc:
        print(
            f"创建失败：{exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        conn.close()

    print("初始超级管理员创建成功。")
    print(f"user_id={user['id']}")
    print(f"username={user['username']}")
    print(f"display_name={user['display_name']}")
    print(f"role={user['role']}")
    print(f"status={user['status']}")
    print("密码和密码哈希未输出。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
