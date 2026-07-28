from __future__ import annotations

import json
import sqlite3

import pytest
from werkzeug.exceptions import (
    BadRequest,
    Forbidden,
    MethodNotAllowed,
)

import app as app_module
from services.v158_auth_service import (
    CSRF_SESSION_KEY,
)
from services.v158_auth_store import (
    AUTH_SCHEMA_SQL,
)


BUSINESS_TABLES = (
    "ai_reports",
    "attendance_battle_configs",
    "compare_cache",
    "identity_history",
    "identity_logs",
    "member_battle_profiles",
    "player_records",
    "risk_records",
    "snapshots",
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
        SECRET_KEY="battle-action-test-secret",
    )

    conn = sqlite3.connect(database)

    try:
        conn.executescript(
            AUTH_SCHEMA_SQL
        )

        conn.execute(
            """
            CREATE TABLE battles (
                id INTEGER PRIMARY KEY,
                battle_name TEXT,
                is_current INTEGER NOT NULL
                    DEFAULT 0
            )
            """
        )

        for table_name in BUSINESS_TABLES:
            if table_name == "member_battle_profiles":
                conn.execute(
                    """
                    CREATE TABLE member_battle_profiles (
                        id INTEGER PRIMARY KEY,
                        battle_id INTEGER,
                        FOREIGN KEY (battle_id)
                            REFERENCES battles(id)
                            ON DELETE NO ACTION
                    )
                    """
                )
            else:
                conn.execute(
                    f"""
                    CREATE TABLE {table_name} (
                        id INTEGER PRIMARY KEY,
                        battle_id INTEGER
                    )
                    """
                )

        conn.executemany(
            """
            INSERT INTO battles (
                id,
                battle_name,
                is_current
            )
            VALUES (?, ?, ?)
            """,
            [
                (
                    1,
                    "当前战场",
                    1,
                ),
                (
                    2,
                    "候选战场",
                    0,
                ),
                (
                    3,
                    "待删除战场",
                    0,
                ),
            ],
        )

        for table_index, table_name in enumerate(
            BUSINESS_TABLES,
            start=1,
        ):
            base_id = table_index * 100

            conn.executemany(
                f"""
                INSERT INTO {table_name} (
                    id,
                    battle_id
                )
                VALUES (?, ?)
                """,
                [
                    (
                        base_id + 1,
                        2,
                    ),
                    (
                        base_id + 2,
                        3,
                    ),
                ],
            )

        conn.commit()

    finally:
        conn.close()

    yield database


def fetch_one(
    sql,
    parameters=(),
):
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


def fetch_all(
    sql,
    parameters=(),
):
    conn = sqlite3.connect(
        app_module.DB_FILE
    )
    conn.row_factory = sqlite3.Row

    try:
        return conn.execute(
            sql,
            parameters,
        ).fetchall()

    finally:
        conn.close()


def audit_count():
    row = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM v158_action_logs
        """
    )

    return int(row["total"])


def call_delete(
    *,
    battle_id=3,
    role="super_admin",
    include_csrf=True,
):
    token = "battle-delete-csrf"
    data = {}

    if include_csrf:
        data["csrf_token"] = token

    with app_module.app.test_request_context(
        f"/battle/delete/{battle_id}",
        method="POST",
        data=data,
        headers={
            "X-Request-ID": "battle-delete-test",
            "User-Agent": "pytest",
        },
    ):
        app_module.session[
            CSRF_SESSION_KEY
        ] = token

        app_module.g.v158_current_user = {
            "id": 11,
            "username": "root-admin",
            "role": role,
        }

        return app_module.battle_delete(
            battle_id
        )


def call_select(
    *,
    battle_id=2,
    role="manager",
    include_csrf=True,
):
    token = "battle-select-csrf"
    data = {}

    if include_csrf:
        data["csrf_token"] = token

    with app_module.app.test_request_context(
        f"/battle/select/{battle_id}",
        method="POST",
        data=data,
        headers={
            "X-Request-ID": "battle-select-test",
            "User-Agent": "pytest",
        },
    ):
        app_module.session[
            CSRF_SESSION_KEY
        ] = token

        app_module.g.v158_current_user = {
            "id": 12,
            "username": "battle-manager",
            "role": role,
        }

        return app_module.battle_select(
            battle_id
        )


def latest_audit():
    return fetch_one(
        """
        SELECT *
        FROM v158_action_logs
        ORDER BY id DESC
        LIMIT 1
        """
    )


def test_get_methods_are_not_registered():
    adapter = app_module.app.url_map.bind(
        "localhost"
    )

    with pytest.raises(MethodNotAllowed):
        adapter.match(
            "/battle/delete/3",
            method="GET",
        )

    with pytest.raises(MethodNotAllowed):
        adapter.match(
            "/battle/select/2",
            method="GET",
        )

    delete_endpoint, _ = adapter.match(
        "/battle/delete/3",
        method="POST",
    )
    select_endpoint, _ = adapter.match(
        "/battle/select/2",
        method="POST",
    )

    assert delete_endpoint == "battle_delete"
    assert select_endpoint == "battle_select"


def test_delete_role_and_csrf_guards_do_not_write():
    with pytest.raises(Forbidden):
        call_delete(
            role="manager",
        )

    with pytest.raises(BadRequest):
        call_delete(
            include_csrf=False,
        )

    assert fetch_one(
        "SELECT id FROM battles WHERE id=3"
    ) is not None
    assert audit_count() == 0


def test_select_role_and_csrf_guards_do_not_write():
    with pytest.raises(Forbidden):
        call_select(
            role="viewer",
        )

    with pytest.raises(BadRequest):
        call_select(
            include_csrf=False,
        )

    current = fetch_one(
        """
        SELECT id
        FROM battles
        WHERE is_current=1
        """
    )

    assert current["id"] == 1
    assert audit_count() == 0


def test_delete_business_blocks_are_audited():
    response = call_delete(
        battle_id=99,
    )

    assert response.status_code == 302

    first_audit = latest_audit()

    assert first_audit["action_key"] == "battle_delete"
    assert first_audit["result_status"] == "blocked"
    assert first_audit["reason"] == "battle_not_found"
    assert first_audit["battle_id"] is None
    assert first_audit["target_id"] == "99"

    response = call_delete(
        battle_id=1,
    )

    assert response.status_code == 302

    second_audit = latest_audit()
    current = fetch_one(
        """
        SELECT *
        FROM battles
        WHERE id=1
        """
    )

    assert current is not None
    assert current["is_current"] == 1
    assert second_audit["action_key"] == "battle_delete"
    assert second_audit["result_status"] == "blocked"
    assert second_audit["reason"] == "current_battle_protected"
    assert second_audit["battle_id"] == 1
    assert audit_count() == 2


def test_select_business_blocks_are_audited():
    response = call_select(
        battle_id=99,
    )

    assert response.status_code == 302

    first_audit = latest_audit()

    assert first_audit["action_key"] == "battle_select"
    assert first_audit["result_status"] == "blocked"
    assert first_audit["reason"] == "battle_not_found"
    assert first_audit["battle_id"] is None
    assert first_audit["target_id"] == "99"

    response = call_select(
        battle_id=1,
    )

    assert response.status_code == 302

    second_audit = latest_audit()
    current = fetch_one(
        """
        SELECT id
        FROM battles
        WHERE is_current=1
        """
    )

    assert current["id"] == 1
    assert second_audit["action_key"] == "battle_select"
    assert second_audit["result_status"] == "blocked"
    assert second_audit["reason"] == "already_current"
    assert second_audit["battle_id"] == 1
    assert audit_count() == 2


def test_delete_cleans_business_data_and_preserves_audit_history():
    conn = sqlite3.connect(
        app_module.DB_FILE
    )

    try:
        conn.execute(
            """
            INSERT INTO v158_action_logs (
                username_snapshot,
                role_snapshot,
                action_key,
                result_status
            )
            VALUES (
                'seed',
                'system',
                'seed_event',
                'success'
            )
            """
        )
        conn.commit()

    finally:
        conn.close()

    response = call_delete()

    assert response.status_code == 302
    assert fetch_one(
        "SELECT id FROM battles WHERE id=3"
    ) is None

    for table_name in BUSINESS_TABLES:
        deleted = fetch_one(
            f"""
            SELECT COUNT(*) AS total
            FROM {table_name}
            WHERE battle_id=3
            """
        )
        retained = fetch_one(
            f"""
            SELECT COUNT(*) AS total
            FROM {table_name}
            WHERE battle_id=2
            """
        )

        assert deleted["total"] == 0
        assert retained["total"] == 1

    audit = latest_audit()

    assert audit["username_snapshot"] == "root-admin"
    assert audit["role_snapshot"] == "super_admin"
    assert audit["battle_id"] == 3
    assert audit["action_key"] == "battle_delete"
    assert audit["result_status"] == "success"
    assert audit["reason"] == "battle_deleted"
    assert audit["request_id"] == "battle-delete-test"

    before_data = json.loads(
        audit["before_data"]
    )
    after_data = json.loads(
        audit["after_data"]
    )

    assert before_data["battle"]["id"] == 3
    assert set(
        before_data["row_counts"]
    ) == set(BUSINESS_TABLES)
    assert all(
        value == 1
        for value in before_data[
            "row_counts"
        ].values()
    )
    assert after_data["deleted"] is True

    seed = fetch_one(
        """
        SELECT *
        FROM v158_action_logs
        WHERE action_key='seed_event'
        """
    )

    assert seed is not None
    assert audit_count() == 2


def test_delete_audit_failure_rolls_back_everything(
    monkeypatch,
):
    def fail_audit(*args, **kwargs):
        raise RuntimeError(
            "audit failed"
        )

    monkeypatch.setattr(
        app_module,
        "record_action_log",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="audit failed",
    ):
        call_delete()

    assert fetch_one(
        "SELECT id FROM battles WHERE id=3"
    ) is not None

    for table_name in BUSINESS_TABLES:
        row = fetch_one(
            f"""
            SELECT COUNT(*) AS total
            FROM {table_name}
            WHERE battle_id=3
            """
        )

        assert row["total"] == 1

    assert audit_count() == 0


def test_manager_select_is_atomic_and_audited():
    response = call_select()

    assert response.status_code == 302

    current_rows = fetch_all(
        """
        SELECT id
        FROM battles
        WHERE is_current=1
        ORDER BY id
        """
    )

    assert [
        row["id"]
        for row in current_rows
    ] == [2]

    audit = latest_audit()

    assert audit["username_snapshot"] == "battle-manager"
    assert audit["role_snapshot"] == "manager"
    assert audit["battle_id"] == 2
    assert audit["action_key"] == "battle_select"
    assert audit["result_status"] == "success"
    assert audit["reason"] == "battle_selected"
    assert audit["request_id"] == "battle-select-test"

    before_data = json.loads(
        audit["before_data"]
    )
    after_data = json.loads(
        audit["after_data"]
    )

    assert before_data["current_battles"] == [
        {
            "id": 1,
            "battle_name": "当前战场",
        }
    ]
    assert before_data["target"]["id"] == 2
    assert after_data["current_battle_id"] == 2


def test_select_audit_failure_rolls_back_switch(
    monkeypatch,
):
    def fail_audit(*args, **kwargs):
        raise RuntimeError(
            "audit failed"
        )

    monkeypatch.setattr(
        app_module,
        "record_action_log",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="audit failed",
    ):
        call_select()

    current_rows = fetch_all(
        """
        SELECT id
        FROM battles
        WHERE is_current=1
        ORDER BY id
        """
    )

    assert [
        row["id"]
        for row in current_rows
    ] == [1]
    assert audit_count() == 0
