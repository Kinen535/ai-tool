from __future__ import annotations

import hmac
import secrets
import sqlite3
import time
from typing import Any, MutableMapping
from urllib.parse import urlsplit

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from services.v158_auth_store import (
    get_user_by_id,
    get_user_by_username,
    get_user_lock_state,
    record_login_event,
    register_login_failure,
    register_login_success,
)


SESSION_USER_ID = "v158_user_id"
SESSION_USERNAME = "v158_username"
SESSION_ROLE = "v158_role"
SESSION_VERSION = "v158_session_version"
SESSION_LOGIN_AT = "v158_login_at"
SESSION_LAST_ACTIVE_AT = "v158_last_active_at"

CSRF_SESSION_KEY = "v158_csrf_token"

AUTH_SESSION_KEYS = (
    SESSION_USER_ID,
    SESSION_USERNAME,
    SESSION_ROLE,
    SESSION_VERSION,
    SESSION_LOGIN_AT,
    SESSION_LAST_ACTIVE_AT,
)

ROLE_LEVELS = {
    "viewer": 10,
    "manager": 20,
    "super_admin": 30,
}

DEFAULT_IDLE_TIMEOUT_SECONDS = 30 * 60
DEFAULT_ABSOLUTE_TIMEOUT_SECONDS = 12 * 60 * 60
DEFAULT_TOUCH_INTERVAL_SECONDS = 60

GENERIC_LOGIN_ERROR = (
    "用户名或密码错误，或账号暂时不可用。"
)

DUMMY_PASSWORD_HASH = generate_password_hash(
    "v158-dummy-authentication-password",
    method="scrypt",
)


def _epoch(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def issue_csrf_token(
    session_data: MutableMapping[str, Any],
    *,
    force: bool = False,
) -> str:
    current = str(
        session_data.get(
            CSRF_SESSION_KEY
        )
        or ""
    )

    if (
        not force
        and 32 <= len(current) <= 256
    ):
        return current

    token = secrets.token_urlsafe(32)

    session_data[
        CSRF_SESSION_KEY
    ] = token

    return token


def validate_csrf_token(
    session_data: MutableMapping[str, Any],
    supplied_token: Any,
) -> bool:
    expected = str(
        session_data.get(
            CSRF_SESSION_KEY
        )
        or ""
    )

    supplied = str(
        supplied_token or ""
    )

    if not expected or not supplied:
        return False

    return hmac.compare_digest(
        expected,
        supplied,
    )


def safe_next_path(
    value: Any,
    default: str = "/",
) -> str:
    candidate = str(value or "").strip()

    if not candidate:
        return default

    if len(candidate) > 500:
        return default

    if any(
        ord(character) < 32
        for character in candidate
    ):
        return default

    if "\\" in candidate:
        return default

    parsed = urlsplit(candidate)

    if parsed.scheme or parsed.netloc:
        return default

    if not candidate.startswith("/"):
        return default

    if candidate.startswith("//"):
        return default

    return candidate


def role_allows(
    actual_role: str,
    required_role: str,
) -> bool:
    actual_level = ROLE_LEVELS.get(
        str(actual_role or ""),
        0,
    )

    required_level = ROLE_LEVELS.get(
        str(required_role or ""),
        10**9,
    )

    return actual_level >= required_level


def is_public_request(
    *,
    path: str,
    endpoint: str | None,
) -> bool:
    path = str(path or "")
    endpoint = str(endpoint or "")

    if endpoint == "static":
        return True

    if path.startswith("/static/"):
        return True

    if path.startswith("/favicon"):
        return True

    if path in {
        "/login",
        "/security/login",
    }:
        return True

    return False


def is_security_admin_path(path: str) -> bool:
    path = str(path or "")

    if path == "/security":
        return True

    if path.startswith("/security/"):
        return path != "/security/login"

    return False


def clear_auth_session(
    session_data: MutableMapping[str, Any],
) -> None:
    for key in AUTH_SESSION_KEYS:
        session_data.pop(key, None)


def establish_auth_session(
    session_data: MutableMapping[str, Any],
    *,
    user: dict[str, Any],
    now_ts: int | None = None,
) -> None:
    now_ts = int(
        now_ts
        if now_ts is not None
        else time.time()
    )

    clear_auth_session(session_data)

    session_data[SESSION_USER_ID] = int(user["id"])
    session_data[SESSION_USERNAME] = str(
        user.get("username") or ""
    )
    session_data[SESSION_ROLE] = str(
        user.get("role") or ""
    )
    session_data[SESSION_VERSION] = int(
        user.get("session_version") or 1
    )
    session_data[SESSION_LOGIN_AT] = now_ts
    session_data[SESSION_LAST_ACTIVE_AT] = now_ts

    if hasattr(session_data, "permanent"):
        session_data.permanent = True


def validate_auth_session(
    conn: sqlite3.Connection,
    session_data: MutableMapping[str, Any],
    *,
    now_ts: int | None = None,
    idle_timeout_seconds: int = (
        DEFAULT_IDLE_TIMEOUT_SECONDS
    ),
    absolute_timeout_seconds: int = (
        DEFAULT_ABSOLUTE_TIMEOUT_SECONDS
    ),
    touch_interval_seconds: int = (
        DEFAULT_TOUCH_INTERVAL_SECONDS
    ),
) -> dict[str, Any]:
    now_ts = int(
        now_ts
        if now_ts is not None
        else time.time()
    )

    user_id = _epoch(
        session_data.get(SESSION_USER_ID)
    )
    session_version = _epoch(
        session_data.get(SESSION_VERSION)
    )
    login_at = _epoch(
        session_data.get(SESSION_LOGIN_AT)
    )
    last_active_at = _epoch(
        session_data.get(SESSION_LAST_ACTIVE_AT)
    )

    def reject(reason: str) -> dict[str, Any]:
        clear_auth_session(session_data)

        return {
            "ok": False,
            "reason": reason,
            "user": None,
        }

    if (
        user_id is None
        or session_version is None
        or login_at is None
        or last_active_at is None
    ):
        return reject("missing_session")

    if login_at > now_ts + 300:
        return reject("invalid_login_time")

    if last_active_at > now_ts + 300:
        return reject("invalid_activity_time")

    if now_ts - login_at > max(
        int(absolute_timeout_seconds),
        1,
    ):
        return reject("absolute_timeout")

    if now_ts - last_active_at > max(
        int(idle_timeout_seconds),
        1,
    ):
        return reject("idle_timeout")

    user = get_user_by_id(
        conn,
        user_id,
    )

    if not user:
        return reject("user_missing")

    if user.get("status") != "active":
        return reject("account_disabled")

    if int(
        user.get("session_version") or 0
    ) != session_version:
        return reject("session_version_changed")

    if now_ts - last_active_at >= max(
        int(touch_interval_seconds),
        1,
    ):
        session_data[
            SESSION_LAST_ACTIVE_AT
        ] = now_ts

    session_data[SESSION_USERNAME] = str(
        user.get("username") or ""
    )
    session_data[SESSION_ROLE] = str(
        user.get("role") or ""
    )

    return {
        "ok": True,
        "reason": "",
        "user": user,
    }


def authenticate_credentials(
    conn: sqlite3.Connection,
    *,
    username: str,
    password: str,
    ip_address: str = "",
    user_agent: str = "",
    request_path: str = "/login",
    lock_after: int = 5,
    lock_minutes: int = 15,
) -> dict[str, Any]:
    username = str(username or "").strip()
    password = str(password or "")

    if conn.in_transaction:
        raise RuntimeError(
            "登录认证前存在未提交事务。"
        )

    conn.execute("BEGIN IMMEDIATE")

    try:
        user = get_user_by_username(
            conn,
            username,
        )

        if not user:
            check_password_hash(
                DUMMY_PASSWORD_HASH,
                password,
            )

            record_login_event(
                conn,
                user_id=None,
                username_snapshot=username,
                event_type="login_failure",
                result_status="failure",
                reason_code="invalid_credentials",
                ip_address=ip_address,
                user_agent=user_agent,
                request_path=request_path,
            )

            conn.commit()

            return {
                "ok": False,
                "reason": "invalid_credentials",
                "message": GENERIC_LOGIN_ERROR,
                "user": None,
                "locked": False,
            }

        user_id = int(user["id"])
        username_snapshot = str(
            user.get("username") or username
        )

        lock_state = get_user_lock_state(
            conn,
            user_id,
        )

        if not lock_state:
            raise RuntimeError(
                "账号锁定状态读取失败。"
            )

        if user.get("status") != "active":
            try:
                check_password_hash(
                    str(user.get("password_hash") or ""),
                    password,
                )
            except Exception:
                check_password_hash(
                    DUMMY_PASSWORD_HASH,
                    password,
                )

            record_login_event(
                conn,
                user_id=user_id,
                username_snapshot=username_snapshot,
                event_type="login_failure",
                result_status="blocked",
                reason_code="account_disabled",
                ip_address=ip_address,
                user_agent=user_agent,
                request_path=request_path,
                session_version=int(
                    user.get("session_version") or 1
                ),
            )

            conn.commit()

            return {
                "ok": False,
                "reason": "account_disabled",
                "message": GENERIC_LOGIN_ERROR,
                "user": None,
                "locked": False,
            }

        if lock_state.get("is_locked"):
            try:
                check_password_hash(
                    str(user.get("password_hash") or ""),
                    password,
                )
            except Exception:
                check_password_hash(
                    DUMMY_PASSWORD_HASH,
                    password,
                )

            record_login_event(
                conn,
                user_id=user_id,
                username_snapshot=username_snapshot,
                event_type="login_failure",
                result_status="blocked",
                reason_code="account_locked",
                ip_address=ip_address,
                user_agent=user_agent,
                request_path=request_path,
                session_version=int(
                    lock_state.get("session_version")
                    or 1
                ),
            )

            conn.commit()

            return {
                "ok": False,
                "reason": "account_locked",
                "message": GENERIC_LOGIN_ERROR,
                "user": None,
                "locked": True,
                "locked_until": (
                    lock_state.get("locked_until")
                ),
            }

        try:
            password_ok = check_password_hash(
                str(user.get("password_hash") or ""),
                password,
            )
        except Exception:
            password_ok = False

        if not password_ok:
            failed_state = register_login_failure(
                conn,
                user_id=user_id,
                lock_after=lock_after,
                lock_minutes=lock_minutes,
            )

            record_login_event(
                conn,
                user_id=user_id,
                username_snapshot=username_snapshot,
                event_type="login_failure",
                result_status="failure",
                reason_code="invalid_credentials",
                ip_address=ip_address,
                user_agent=user_agent,
                request_path=request_path,
                session_version=int(
                    failed_state.get(
                        "session_version"
                    )
                    or 1
                ),
            )

            if failed_state.get("just_locked"):
                record_login_event(
                    conn,
                    user_id=user_id,
                    username_snapshot=(
                        username_snapshot
                    ),
                    event_type="account_locked",
                    result_status="blocked",
                    reason_code=(
                        "too_many_login_failures"
                    ),
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_path=request_path,
                    session_version=int(
                        failed_state.get(
                            "session_version"
                        )
                        or 1
                    ),
                )

            conn.commit()

            return {
                "ok": False,
                "reason": "invalid_credentials",
                "message": GENERIC_LOGIN_ERROR,
                "user": None,
                "locked": bool(
                    failed_state.get("is_locked")
                ),
                "just_locked": bool(
                    failed_state.get("just_locked")
                ),
                "locked_until": (
                    failed_state.get("locked_until")
                ),
            }

        authenticated_user = register_login_success(
            conn,
            user_id=user_id,
            ip_address=ip_address,
        )

        record_login_event(
            conn,
            user_id=user_id,
            username_snapshot=username_snapshot,
            event_type="login_success",
            result_status="success",
            reason_code="",
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
            session_version=int(
                authenticated_user.get(
                    "session_version"
                )
                or 1
            ),
        )

        conn.commit()

        return {
            "ok": True,
            "reason": "",
            "message": "",
            "user": authenticated_user,
            "locked": False,
        }

    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
