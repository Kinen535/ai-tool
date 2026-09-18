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

    app_module.app.config.update(
        TESTING=True,
    )

    conn = sqlite3.connect(database)

    try:
        conn.executescript(
            AUTH_SCHEMA_SQL
        )

        conn.executescript(
            """
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY,
                snapshot_time TEXT NOT NULL,
                battle_id INTEGER NOT NULL,
                is_deleted INTEGER NOT NULL
                    DEFAULT 0
            );

            CREATE TABLE player_records (
                id INTEGER PRIMARY KEY,
                snapshot_time TEXT NOT NULL,
                battle_id INTEGER NOT NULL,
                is_deleted INTEGER NOT NULL
                    DEFAULT 0
            );

            CREATE TABLE compare_cache (
                id INTEGER PRIMARY KEY,
                battle_id INTEGER NOT NULL
            );
            """
        )

        conn.execute(
            """
            INSERT INTO snapshots (
                id,
                snapshot_time,
                battle_id,
                is_deleted
            )
            VALUES (1, '2026-07-27 08:00:00', 7, 0)
            """
        )

        conn.executemany(
            """
            INSERT INTO player_records (
                id,
                snapshot_time,
                battle_id,
                is_deleted
            )
            VALUES (?, ?, ?, 0)
            """,
            [
                (
                    1,
                    "2026-07-27 08:00:00",
                    7,
                ),
                (
                    2,
                    "2026-07-27 08:00:00",
                    7,
                ),
                (
                    3,
                    "2026-07-27 08:00:00",
                    8,
                ),
            ],
        )

        conn.executemany(
            """
            INSERT INTO compare_cache (
                id,
                battle_id
            )
            VALUES (?, ?)
            """,
            [
                (1, 7),
                (2, 8),
            ],
        )

        conn.commit()

    finally:
        conn.close()


def database_row(
    sql: str,
):
    conn = sqlite3.connect(
        app_module.DB_FILE
    )
    conn.row_factory = sqlite3.Row

    try:
        return conn.execute(
            sql
        ).fetchone()
    finally:
        conn.close()


def call_snapshot_delete(
    *,
    snapshot_id: int = 1,
    role: str = "super_admin",
    include_csrf: bool = True,
):
    token = "snapshot-delete-csrf-token"

    data = {}

    if include_csrf:
        data["csrf_token"] = token

    with app_module.app.test_request_context(
        f"/snapshot/delete/{snapshot_id}",
        method="POST",
        data=data,
        headers={
            "User-Agent": "pytest",
            "X-Request-ID": (
                "snapshot-delete-test"
            ),
        },
    ):
        app_module.session[
            CSRF_SESSION_KEY
        ] = token

        app_module.g.v158_current_user = {
            "id": 1,
            "username": "root-admin",
            "role": role,
        }

        app_module.g.v155_access_context = {
            "workspace_id": 1,
            "battle_ids": (7, 8),
            "current_battle_id": 7,
            "permissions": (),
        }

        return app_module.snapshot_delete(
            snapshot_id
        )


def test_manager_cannot_delete_snapshot():
    with pytest.raises(Forbidden):
        call_snapshot_delete(
            role="manager",
        )

    row = database_row(
        """
        SELECT is_deleted
        FROM snapshots
        WHERE id=1
        """
    )

    assert row["is_deleted"] == 0

    count = database_row(
        """
        SELECT COUNT(*) AS total
        FROM v158_action_logs
        """
    )

    assert count["total"] == 0


def test_snapshot_delete_requires_csrf():
    with pytest.raises(BadRequest):
        call_snapshot_delete(
            include_csrf=False,
        )

    row = database_row(
        """
        SELECT is_deleted
        FROM snapshots
        WHERE id=1
        """
    )

    assert row["is_deleted"] == 0


def test_missing_snapshot_records_blocked_audit():
    response = call_snapshot_delete(
        snapshot_id=99,
    )

    assert response.status_code == 302

    event = database_row(
        """
        SELECT
            action_key,
            result_status,
            reason,
            target_id
        FROM v158_action_logs
        ORDER BY id DESC
        LIMIT 1
        """
    )

    assert event["action_key"] == (
        "snapshot_delete"
    )
    assert event["result_status"] == (
        "blocked"
    )
    assert event["reason"] == (
        "snapshot_not_found"
    )
    assert event["target_id"] == "99"


def test_super_admin_delete_is_atomic_and_audited():
    response = call_snapshot_delete()

    assert response.status_code == 302

    snapshot = database_row(
        """
        SELECT is_deleted
        FROM snapshots
        WHERE id=1
        """
    )

    assert snapshot["is_deleted"] == 1

    deleted_players = database_row(
        """
        SELECT COUNT(*) AS total
        FROM player_records
        WHERE battle_id=7
          AND is_deleted=1
        """
    )

    assert deleted_players["total"] == 2

    other_battle = database_row(
        """
        SELECT is_deleted
        FROM player_records
        WHERE battle_id=8
        """
    )

    assert other_battle["is_deleted"] == 0

    cache_seven = database_row(
        """
        SELECT COUNT(*) AS total
        FROM compare_cache
        WHERE battle_id=7
        """
    )

    cache_eight = database_row(
        """
        SELECT COUNT(*) AS total
        FROM compare_cache
        WHERE battle_id=8
        """
    )

    assert cache_seven["total"] == 0
    assert cache_eight["total"] == 1

    event = database_row(
        """
        SELECT
            username_snapshot,
            role_snapshot,
            battle_id,
            action_key,
            result_status,
            request_method,
            request_path,
            request_id,
            target_id
        FROM v158_action_logs
        ORDER BY id DESC
        LIMIT 1
        """
    )

    assert event["username_snapshot"] == (
        "root-admin"
    )
    assert event["role_snapshot"] == (
        "super_admin"
    )
    assert event["battle_id"] == 7
    assert event["action_key"] == (
        "snapshot_delete"
    )
    assert event["result_status"] == (
        "success"
    )
    assert event["request_method"] == (
        "POST"
    )
    assert event["request_path"] == (
        "/snapshot/delete/1"
    )
    assert event["request_id"] == (
        "snapshot-delete-test"
    )
    assert event["target_id"] == "1"
