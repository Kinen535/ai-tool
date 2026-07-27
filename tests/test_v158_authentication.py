from __future__ import annotations

import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from services.v158_auth_service import (
    AUTH_SESSION_KEYS,
    SESSION_LAST_ACTIVE_AT,
    authenticate_credentials,
    establish_auth_session,
    issue_csrf_token,
    role_allows,
    safe_next_path,
    validate_auth_session,
    validate_csrf_token,
)
from services.v158_auth_store import AUTH_SCHEMA_SQL


TEST_PASSWORD = "V158-Test-Password-2026!"


@pytest.fixture()
def auth_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(AUTH_SCHEMA_SQL)
    conn.commit()

    try:
        yield conn
    finally:
        conn.close()


def insert_user(
    conn: sqlite3.Connection,
    *,
    username: str = "admin",
    password: str = TEST_PASSWORD,
    role: str = "super_admin",
    status: str = "active",
    session_version: int = 1,
) -> dict:
    cursor = conn.execute(
        """
        INSERT INTO v158_users (
            username,
            password_hash,
            display_name,
            role,
            status,
            session_version
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            generate_password_hash(password),
            "测试用户",
            role,
            status,
            session_version,
        ),
    )
    conn.commit()

    row = conn.execute(
        """
        SELECT *
        FROM v158_users
        WHERE id=?
        """,
        (cursor.lastrowid,),
    ).fetchone()

    assert row is not None
    return dict(row)


def test_csrf_token_rotation_and_validation() -> None:
    session_data: dict = {}

    token = issue_csrf_token(session_data)

    assert token
    assert validate_csrf_token(
        session_data,
        token,
    )
    assert not validate_csrf_token(
        session_data,
        "incorrect-token",
    )
    assert issue_csrf_token(session_data) == token

    rotated = issue_csrf_token(
        session_data,
        force=True,
    )

    assert rotated
    assert rotated != token
    assert validate_csrf_token(
        session_data,
        rotated,
    )


def test_safe_next_path_blocks_external_redirects() -> None:
    assert safe_next_path(
        "/compare?scope=alliance",
        default="/",
    ) == "/compare?scope=alliance"

    assert safe_next_path(
        "https://evil.example/login",
        default="/",
    ) == "/"

    assert safe_next_path(
        "//evil.example/login",
        default="/",
    ) == "/"


def test_role_hierarchy() -> None:
    assert role_allows(
        "super_admin",
        "super_admin",
    )
    assert role_allows(
        "super_admin",
        "manager",
    )
    assert role_allows(
        "super_admin",
        "viewer",
    )

    assert role_allows(
        "manager",
        "viewer",
    )
    assert not role_allows(
        "manager",
        "super_admin",
    )

    assert role_allows(
        "viewer",
        "viewer",
    )
    assert not role_allows(
        "viewer",
        "manager",
    )


def test_session_validation_refreshes_activity(
    auth_conn: sqlite3.Connection,
) -> None:
    user = insert_user(auth_conn)
    session_data: dict = {}

    establish_auth_session(
        session_data,
        user=user,
        now_ts=1000,
    )

    result = validate_auth_session(
        auth_conn,
        session_data,
        now_ts=1061,
    )

    assert result["ok"] is True
    assert result["user"]["username"] == "admin"
    assert session_data[
        SESSION_LAST_ACTIVE_AT
    ] == 1061


def test_idle_timeout_clears_session(
    auth_conn: sqlite3.Connection,
) -> None:
    user = insert_user(auth_conn)
    session_data: dict = {}

    establish_auth_session(
        session_data,
        user=user,
        now_ts=1000,
    )

    result = validate_auth_session(
        auth_conn,
        session_data,
        now_ts=2801,
    )

    assert result["ok"] is False
    assert result["reason"] == "idle_timeout"

    for key in AUTH_SESSION_KEYS:
        assert key not in session_data


def test_session_version_change_rejects_session(
    auth_conn: sqlite3.Connection,
) -> None:
    user = insert_user(
        auth_conn,
        session_version=1,
    )
    session_data: dict = {}

    establish_auth_session(
        session_data,
        user=user,
        now_ts=1000,
    )

    auth_conn.execute(
        """
        UPDATE v158_users
        SET session_version=2
        WHERE id=?
        """,
        (user["id"],),
    )
    auth_conn.commit()

    result = validate_auth_session(
        auth_conn,
        session_data,
        now_ts=1100,
    )

    assert result["ok"] is False
    assert (
        result["reason"]
        == "session_version_changed"
    )

    for key in AUTH_SESSION_KEYS:
        assert key not in session_data


def test_successful_authentication_records_login(
    auth_conn: sqlite3.Connection,
) -> None:
    user = insert_user(auth_conn)

    result = authenticate_credentials(
        auth_conn,
        username="admin",
        password=TEST_PASSWORD,
        ip_address="127.0.0.1",
        user_agent="pytest",
        request_path="/login",
    )

    assert result["ok"] is True
    assert result["locked"] is False
    assert result["user"]["id"] == user["id"]

    state = auth_conn.execute(
        """
        SELECT
            failed_login_count,
            locked_until,
            last_login_ip
        FROM v158_users
        WHERE id=?
        """,
        (user["id"],),
    ).fetchone()

    assert state is not None
    assert state["failed_login_count"] == 0
    assert state["locked_until"] is None
    assert state["last_login_ip"] == "127.0.0.1"

    event = auth_conn.execute(
        """
        SELECT
            event_type,
            result_status
        FROM v158_login_logs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    assert event is not None
    assert event["event_type"] == "login_success"
    assert event["result_status"] == "success"


def test_five_failures_lock_account(
    auth_conn: sqlite3.Connection,
) -> None:
    user = insert_user(auth_conn)

    result = None

    for _ in range(5):
        result = authenticate_credentials(
            auth_conn,
            username="admin",
            password="wrong-password",
            ip_address="127.0.0.2",
            user_agent="pytest",
            request_path="/login",
        )

    assert result is not None
    assert result["ok"] is False
    assert result["locked"] is True
    assert result["just_locked"] is True

    state = auth_conn.execute(
        """
        SELECT
            failed_login_count,
            locked_until,
            session_version
        FROM v158_users
        WHERE id=?
        """,
        (user["id"],),
    ).fetchone()

    assert state is not None
    assert state["failed_login_count"] == 5
    assert state["locked_until"] is not None
    assert state["session_version"] == 2

    events = auth_conn.execute(
        """
        SELECT event_type
        FROM v158_login_logs
        ORDER BY id
        """
    ).fetchall()

    event_types = [
        row["event_type"]
        for row in events
    ]

    assert event_types.count(
        "login_failure"
    ) == 5
    assert event_types.count(
        "account_locked"
    ) == 1

    blocked = authenticate_credentials(
        auth_conn,
        username="admin",
        password=TEST_PASSWORD,
        ip_address="127.0.0.2",
        user_agent="pytest",
        request_path="/login",
    )

    assert blocked["ok"] is False
    assert blocked["reason"] == "account_locked"
    assert blocked["locked"] is True


def test_disabled_account_is_blocked(
    auth_conn: sqlite3.Connection,
) -> None:
    insert_user(
        auth_conn,
        status="disabled",
    )

    result = authenticate_credentials(
        auth_conn,
        username="admin",
        password=TEST_PASSWORD,
        ip_address="127.0.0.3",
        user_agent="pytest",
        request_path="/login",
    )

    assert result["ok"] is False
    assert result["reason"] == "account_disabled"
    assert result["user"] is None

    event = auth_conn.execute(
        """
        SELECT
            event_type,
            result_status,
            reason_code
        FROM v158_login_logs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    assert event is not None
    assert event["event_type"] == "login_failure"
    assert event["result_status"] == "blocked"
    assert event["reason_code"] == "account_disabled"


def test_unknown_account_uses_generic_failure(
    auth_conn: sqlite3.Connection,
) -> None:
    result = authenticate_credentials(
        auth_conn,
        username="unknown-user",
        password="unknown-password",
        ip_address="127.0.0.4",
        user_agent="pytest",
        request_path="/login",
    )

    assert result["ok"] is False
    assert result["reason"] == "invalid_credentials"
    assert result["user"] is None
    assert result["locked"] is False

    assert (
        auth_conn.execute(
            "SELECT COUNT(*) FROM v158_users"
        ).fetchone()[0]
        == 0
    )

    event = auth_conn.execute(
        """
        SELECT
            username_snapshot,
            event_type,
            reason_code
        FROM v158_login_logs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    assert event is not None
    assert (
        event["username_snapshot"]
        == "unknown-user"
    )
    assert event["event_type"] == "login_failure"
    assert event["reason_code"] == "invalid_credentials"
