from __future__ import annotations

import sqlite3

import pytest
from werkzeug.exceptions import (
    BadRequest,
    Forbidden,
)

import app as app_module
from services.v158_auth_service import (
    CSRF_SESSION_KEY,
)
from services.v158_auth_store import (
    AUTH_SCHEMA_SQL,
)


@pytest.fixture(autouse=True)
def temporary_database(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "snapshots.db"

    monkeypatch.setattr(
        app_module,
        "DB_FILE",
        database,
    )

    for function_name in (
        "calculate_stall",
        "calculate_stall_penalty",
        "calculate_risk",
        "sync_member_profiles",
        "calculate_identity_score",
        "sync_identity",
    ):
        monkeypatch.setattr(
            app_module,
            function_name,
            lambda *args, **kwargs: None,
        )

    conn = sqlite3.connect(database)

    try:
        conn.executescript(AUTH_SCHEMA_SQL)

        conn.executescript(
            """
            CREATE TABLE battles (
                id INTEGER PRIMARY KEY,
                is_current INTEGER NOT NULL
            );

            CREATE TABLE member_battle_profiles (
                battle_id INTEGER NOT NULL,
                member_name TEXT NOT NULL,
                role_tag TEXT,
                role_desc TEXT,
                role_rule TEXT,
                role_weight REAL,
                identity_score REAL,
                is_protected INTEGER,
                exempt_stall INTEGER
            );

            CREATE TABLE player_records (
                id INTEGER PRIMARY KEY,
                battle_id INTEGER NOT NULL,
                member TEXT NOT NULL,
                snapshot_time TEXT,
                role_tag TEXT,
                role_desc TEXT,
                role_rule TEXT,
                role_weight REAL,
                is_protected INTEGER,
                exempt_stall INTEGER
            );

            CREATE TABLE identity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                battle_id INTEGER,
                member_name TEXT,
                old_role TEXT,
                new_role TEXT,
                old_score REAL,
                new_score REAL,
                old_protect INTEGER,
                new_protect INTEGER,
                old_exempt INTEGER,
                new_exempt INTEGER,
                operator TEXT,
                created_at TEXT
            );

            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY,
                snapshot_time TEXT,
                battle_id INTEGER,
                is_deleted INTEGER
            );
            """
        )

        conn.executemany(
            "INSERT INTO battles VALUES (?, ?)",
            [
                (1, 1),
                (2, 0),
            ],
        )

        conn.execute(
            """
            INSERT INTO member_battle_profiles
            VALUES (
                1, '成员甲', 'member', '',
                'normal', 1, 50, 0, 0
            )
            """
        )

        conn.executemany(
            """
            INSERT INTO player_records
            VALUES (
                ?, ?, '成员甲',
                '2026-07-27 08:00:00',
                'member', '', 'normal',
                1, 0, 0
            )
            """,
            [
                (1, 1),
                (2, 2),
            ],
        )

        conn.execute(
            """
            INSERT INTO snapshots
            VALUES (
                1,
                '2026-07-27 08:00:00',
                1,
                0
            )
            """
        )

        conn.commit()

    finally:
        conn.close()


def fetch_one(sql, parameters=()):
    conn = sqlite3.connect(
        app_module.DB_FILE
    )
    conn.row_factory = sqlite3.Row

    try:
        return conn.execute(
            sql,
            parameters,
        ).fetchone()

    finally:
        conn.close()


def call_edit(
    *,
    role="manager",
    include_csrf=True,
):
    token = "identity-edit-token"

    data = {
        "role_tag": "core",
        "role_desc": "核心作战成员",
        "role_rule": "normal",
        "role_weight": "1.5",
        "is_protected": "on",
    }

    if include_csrf:
        data["csrf_token"] = token

    with app_module.app.test_request_context(
        "/identity/edit/成员甲",
        method="POST",
        data=data,
        headers={
            "X-Request-ID": (
                "identity-edit-test"
            ),
            "User-Agent": "pytest",
        },
    ):
        app_module.session[
            CSRF_SESSION_KEY
        ] = token

        app_module.g.v158_current_user = {
            "id": 8,
            "username": "manager-one",
            "role": role,
        }

        app_module.g.v155_access_context = {
            "workspace_id": 1,
            "battle_ids": (1, 2),
            "current_battle_id": 1,
            "permissions": (),
        }

        return app_module.identity_edit(
            "成员甲"
        )


def test_viewer_cannot_edit_identity():
    with pytest.raises(Forbidden):
        call_edit(role="viewer")

    profile = fetch_one(
        """
        SELECT role_tag
        FROM member_battle_profiles
        """
    )

    assert profile["role_tag"] == "member"


def test_identity_edit_requires_csrf():
    with pytest.raises(BadRequest):
        call_edit(include_csrf=False)

    profile = fetch_one(
        """
        SELECT role_tag
        FROM member_battle_profiles
        """
    )

    assert profile["role_tag"] == "member"


def test_manager_edit_is_synced_and_audited():
    response = call_edit()

    assert response.status_code == 302

    profile = fetch_one(
        """
        SELECT *
        FROM member_battle_profiles
        WHERE battle_id=1
          AND member_name='成员甲'
        """
    )

    assert profile["role_tag"] == "core"
    assert profile["is_protected"] == 1

    current_record = fetch_one(
        """
        SELECT role_tag, is_protected
        FROM player_records
        WHERE battle_id=1
        """
    )

    other_record = fetch_one(
        """
        SELECT role_tag
        FROM player_records
        WHERE battle_id=2
        """
    )

    assert current_record["role_tag"] == "core"
    assert current_record["is_protected"] == 1
    assert other_record["role_tag"] == "member"

    history = fetch_one(
        """
        SELECT operator, old_role, new_role
        FROM identity_logs
        ORDER BY id DESC
        LIMIT 1
        """
    )

    assert history["operator"] == "manager-one"
    assert history["old_role"] == "member"
    assert history["new_role"] == "core"

    audit = fetch_one(
        """
        SELECT
            action_key,
            result_status,
            username_snapshot,
            role_snapshot,
            battle_id,
            request_id
        FROM v158_action_logs
        ORDER BY id DESC
        LIMIT 1
        """
    )

    assert audit["action_key"] == "identity_edit"
    assert audit["result_status"] == "success"
    assert audit["username_snapshot"] == "manager-one"
    assert audit["role_snapshot"] == "manager"
    assert audit["battle_id"] == 1
    assert audit["request_id"] == "identity-edit-test"


def test_audit_failure_rolls_back_everything(
    monkeypatch,
):
    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(
        app_module,
        "record_action_log",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="audit failed",
    ):
        call_edit()

    profile = fetch_one(
        """
        SELECT role_tag, is_protected
        FROM member_battle_profiles
        """
    )

    assert profile["role_tag"] == "member"
    assert profile["is_protected"] == 0

    player = fetch_one(
        """
        SELECT role_tag
        FROM player_records
        WHERE battle_id=1
        """
    )

    assert player["role_tag"] == "member"

    history = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM identity_logs
        """
    )

    assert history["total"] == 0
