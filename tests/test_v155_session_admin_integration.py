from __future__ import annotations

import hashlib
import sqlite3

import pytest

from services.v158_auth_store import (
    create_user,
    ensure_v158_auth_tables,
)

from services.v155_session_admin_service import (
    build_session_admin_report,
    revoke_all_user_sessions,
    revoke_single_session,
    set_session_policy,
)


SESSION_SCHEMA = """
CREATE TABLE v155_user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id INTEGER NOT NULL,

    session_key_hash TEXT NOT NULL UNIQUE,

    session_version INTEGER NOT NULL,

    status TEXT NOT NULL
        CHECK (
            status IN (
                'active',
                'revoked',
                'logged_out',
                'expired'
            )
        ),

    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,

    revoked_at TEXT,
    revoke_reason TEXT,
    revoked_by_user_id INTEGER,

    login_ip TEXT NOT NULL DEFAULT '',
    last_ip TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    device_label TEXT NOT NULL DEFAULT '',

    FOREIGN KEY(user_id)
        REFERENCES v158_users(id)
        ON DELETE CASCADE,

    FOREIGN KEY(revoked_by_user_id)
        REFERENCES v158_users(id)
        ON DELETE SET NULL
);

CREATE TABLE v155_user_session_policies (
    user_id INTEGER PRIMARY KEY,

    max_active_sessions INTEGER NOT NULL
        CHECK (
            max_active_sessions
            BETWEEN 1 AND 10
        ),

    updated_at TEXT NOT NULL,

    updated_by_user_id INTEGER,

    FOREIGN KEY(user_id)
        REFERENCES v158_users(id)
        ON DELETE CASCADE,

    FOREIGN KEY(updated_by_user_id)
        REFERENCES v158_users(id)
        ON DELETE SET NULL
);
"""


@pytest.fixture
def session_env(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "V155_SESSION_REGISTRY_ENFORCEMENT",
        "1",
    )

    db_path = (
        tmp_path
        / "session_admin.sqlite3"
    )

    conn = sqlite3.connect(
        str(db_path)
    )

    conn.row_factory = (
        sqlite3.Row
    )

    conn.execute(
        "PRAGMA foreign_keys=ON"
    )

    ensure_v158_auth_tables(
        conn
    )

    admin_id = create_user(
        conn,
        username="admina",
        password_hash="x" * 80,
        display_name="Admin",
        role="super_admin",
        status="active",
        must_change_password=False,
    )

    target_id = create_user(
        conn,
        username="targeta",
        password_hash="y" * 80,
        display_name="Target",
        role="viewer",
        status="active",
        must_change_password=False,
    )

    viewer_id = create_user(
        conn,
        username="viewera",
        password_hash="z" * 80,
        display_name="Viewer",
        role="viewer",
        status="active",
        must_change_password=False,
    )

    conn.executescript(
        SESSION_SCHEMA
    )

    conn.commit()

    yield (
        conn,
        admin_id,
        target_id,
        viewer_id,
    )

    conn.close()


def _insert_session(
    conn,
    *,
    user_id,
    marker,
    session_version=1,
):
    digest = hashlib.sha256(
        marker.encode(
            "utf-8"
        )
    ).hexdigest()

    cursor = conn.execute(
        """
        INSERT INTO v155_user_sessions (
            user_id,
            session_key_hash,
            session_version,
            status,
            created_at,
            last_seen_at,
            expires_at,
            login_ip,
            last_ip,
            user_agent,
            device_label
        )
        VALUES (
            ?, ?, ?, 'active',
            ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            int(user_id),
            digest,
            int(session_version),
            "2026-08-30T00:00:00Z",
            "2026-08-30T00:00:00Z",
            "2099-01-01T00:00:00Z",
            "10.0.0.1",
            "10.0.0.2",
            "pytest-agent",
            "pytest-device",
        ),
    )

    conn.commit()

    return int(
        cursor.lastrowid
    )


def test_report_has_no_secret_material(
    session_env,
):
    (
        conn,
        admin_id,
        target_id,
        _viewer_id,
    ) = session_env

    _insert_session(
        conn,
        user_id=target_id,
        marker="report-secret-test",
    )

    report = (
        build_session_admin_report(
            conn,
            actor_user_id=admin_id,
        )
    )

    assert report[
        "registry_schema_ready"
    ] is True

    assert report[
        "registry_enforced"
    ] is True

    assert report[
        "write_ready"
    ] is True

    text = repr(report)

    assert (
        "session_key_hash"
        not in text
    )

    assert (
        "v155_session_id"
        not in text
    )

    target = next(
        item
        for item in report[
            "accounts"
        ]
        if int(
            item["user"]["id"]
        )
        == int(target_id)
    )

    assert (
        target[
            "max_active_sessions"
        ]
        == 2
    )

    assert (
        target[
            "active_session_count"
        ]
        == 1
    )


def test_single_revoke_is_owned_and_no_version_bump(
    session_env,
):
    (
        conn,
        admin_id,
        target_id,
        _viewer_id,
    ) = session_env

    row_id = _insert_session(
        conn,
        user_id=target_id,
        marker="single-revoke",
    )

    before_version = int(
        conn.execute(
            """
            SELECT session_version
            FROM v158_users
            WHERE id=?
            """,
            (
                target_id,
            ),
        ).fetchone()[0]
    )

    result = (
        revoke_single_session(
            conn,
            actor_user_id=admin_id,
            target_user_id=target_id,
            session_row_id=row_id,
            audit={
                "request_method": "POST",
                "request_path": (
                    "/security/sessions/revoke"
                ),
            },
        )
    )

    assert result["ok"] is True
    assert result["changed"] is True

    status = conn.execute(
        """
        SELECT status
        FROM v155_user_sessions
        WHERE id=?
        """,
        (
            row_id,
        ),
    ).fetchone()[0]

    assert status == "revoked"

    after_version = int(
        conn.execute(
            """
            SELECT session_version
            FROM v158_users
            WHERE id=?
            """,
            (
                target_id,
            ),
        ).fetchone()[0]
    )

    assert (
        after_version
        == before_version
    )

    audit_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM v158_action_logs
            WHERE
                action_key=
                    'session_revoke_single'
                AND target_id=?
                AND result_status='success'
            """,
            (
                str(target_id),
            ),
        ).fetchone()[0]
    )

    assert audit_count == 1


def test_single_revoke_cannot_cross_account(
    session_env,
):
    (
        conn,
        admin_id,
        target_id,
        viewer_id,
    ) = session_env

    viewer_session_id = (
        _insert_session(
            conn,
            user_id=viewer_id,
            marker="cross-account",
        )
    )

    result = (
        revoke_single_session(
            conn,
            actor_user_id=admin_id,
            target_user_id=target_id,
            session_row_id=(
                viewer_session_id
            ),
            audit={
                "request_method": "POST",
                "request_path": (
                    "/security/sessions/revoke"
                ),
            },
        )
    )

    assert result["ok"] is False

    status = conn.execute(
        """
        SELECT status
        FROM v155_user_sessions
        WHERE id=?
        """,
        (
            viewer_session_id,
        ),
    ).fetchone()[0]

    assert status == "active"


def test_policy_lowering_does_not_auto_kick(
    session_env,
):
    (
        conn,
        admin_id,
        target_id,
        _viewer_id,
    ) = session_env

    _insert_session(
        conn,
        user_id=target_id,
        marker="policy-1",
    )

    _insert_session(
        conn,
        user_id=target_id,
        marker="policy-2",
    )

    result = (
        set_session_policy(
            conn,
            actor_user_id=admin_id,
            target_user_id=target_id,
            max_active_sessions=1,
            audit={
                "request_method": "POST",
                "request_path": (
                    "/security/sessions/policy"
                ),
            },
        )
    )

    assert result["ok"] is True

    policy = int(
        conn.execute(
            """
            SELECT max_active_sessions
            FROM v155_user_session_policies
            WHERE user_id=?
            """,
            (
                target_id,
            ),
        ).fetchone()[0]
    )

    assert policy == 1

    active_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM v155_user_sessions
            WHERE
                user_id=?
                AND status='active'
            """,
            (
                target_id,
            ),
        ).fetchone()[0]
    )

    assert active_count == 2


def test_revoke_all_bumps_version_and_revokes_registry(
    session_env,
):
    (
        conn,
        admin_id,
        target_id,
        _viewer_id,
    ) = session_env

    _insert_session(
        conn,
        user_id=target_id,
        marker="all-1",
    )

    _insert_session(
        conn,
        user_id=target_id,
        marker="all-2",
    )

    before_version = int(
        conn.execute(
            """
            SELECT session_version
            FROM v158_users
            WHERE id=?
            """,
            (
                target_id,
            ),
        ).fetchone()[0]
    )

    result = (
        revoke_all_user_sessions(
            conn,
            actor_user_id=admin_id,
            target_user_id=target_id,
            audit={
                "request_method": "POST",
                "request_path": (
                    "/security/sessions/revoke-all"
                ),
            },
        )
    )

    assert result["ok"] is True

    after_version = int(
        conn.execute(
            """
            SELECT session_version
            FROM v158_users
            WHERE id=?
            """,
            (
                target_id,
            ),
        ).fetchone()[0]
    )

    assert (
        after_version
        == before_version + 1
    )

    active_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM v155_user_sessions
            WHERE
                user_id=?
                AND status='active'
            """,
            (
                target_id,
            ),
        ).fetchone()[0]
    )

    assert active_count == 0

    revoked_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM v155_user_sessions
            WHERE
                user_id=?
                AND status='revoked'
            """,
            (
                target_id,
            ),
        ).fetchone()[0]
    )

    assert revoked_count == 2


def test_non_super_admin_cannot_change_policy(
    session_env,
):
    (
        conn,
        _admin_id,
        target_id,
        viewer_id,
    ) = session_env

    result = (
        set_session_policy(
            conn,
            actor_user_id=viewer_id,
            target_user_id=target_id,
            max_active_sessions=1,
        )
    )

    assert result["ok"] is False

    count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM v155_user_session_policies
            WHERE user_id=?
            """,
            (
                target_id,
            ),
        ).fetchone()[0]
    )

    assert count == 0


def test_session_destructive_actions_require_confirmation_ux():
    with open(
        "templates/security_sessions.html",
        encoding="utf-8",
    ) as handle:
        template = handle.read()

    expected_confirmations = (
        "确认注销这个登录设备？该设备的当前会话将立即失效；如果这是你正在使用的设备，本次登录也会失效。",
        "确认注销该账号的全部设备？该账号现有登录会全部失效；如果包含你当前正在使用的设备，本次登录也会失效。",
    )

    for message in expected_confirmations:
        assert (
            f'onsubmit="return confirm(\'{message}\');"'
            in template
        )

    assert (
        template.count(
            'onsubmit="return confirm('
        )
        == 2
    )
