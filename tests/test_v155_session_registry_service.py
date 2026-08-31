from __future__ import annotations

import importlib.util
import sqlite3
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path

import pytest

from services.v155_session_registry_service import (
    DEFAULT_MAX_ACTIVE_SESSIONS,
    ForeignKeysRequired,
    SessionLimitExceeded,
    TransactionOwnershipError,
    create_registered_session,
    hash_session_identifier,
    list_user_sessions,
    mark_current_session_logged_out,
    revoke_all_registry_sessions,
    revoke_session_by_id,
    set_max_active_sessions,
    touch_registered_session,
    validate_registered_session,
)


ROOT = Path(__file__).resolve().parents[1]

MIGRATION_PATH = (
    ROOT
    / "scripts/migrate_v155_a6_user_sessions.py"
)


def _load_migration_module():
    spec = (
        importlib.util.spec_from_file_location(
            "a6_session_migration_candidate",
            MIGRATION_PATH,
        )
    )

    assert spec is not None
    assert spec.loader is not None

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


MIGRATION = _load_migration_module()


def utc(
    year=2026,
    month=8,
    day=30,
    hour=8,
    minute=0,
    second=0,
):
    return datetime(
        year,
        month,
        day,
        hour,
        minute,
        second,
        tzinfo=timezone.utc,
    )


@pytest.fixture
def conn():
    db = sqlite3.connect(
        ":memory:"
    )

    db.row_factory = sqlite3.Row

    db.execute(
        "PRAGMA foreign_keys=ON"
    )

    db.execute(
        """
        CREATE TABLE v158_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            session_version INTEGER NOT NULL DEFAULT 1
                CHECK (session_version >= 1)
        )
        """
    )

    db.executemany(
        """
        INSERT INTO v158_users (
            username,
            session_version
        )
        VALUES (?, ?)
        """,
        [
            ("user1", 1),
            ("admin", 1),
            ("user3", 1),
        ],
    )

    db.commit()

    MIGRATION.apply_migration(
        db
    )

    yield db

    db.close()


def create_one(
    conn,
    *,
    user_id=1,
    session_version=1,
    now=None,
    minutes=60,
):
    now = now or utc()

    return create_registered_session(
        conn,
        user_id=user_id,
        session_version=session_version,
        expires_at=(
            now
            + timedelta(
                minutes=minutes
            )
        ),
        login_ip="10.0.0.1",
        user_agent="pytest-browser",
        device_label="Test Device",
        now=now,
    )


def test_migration_is_idempotent(conn):
    MIGRATION.apply_migration(
        conn
    )

    tables = {
        row[0]
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """
        )
    }

    assert (
        "v155_user_sessions"
        in tables
    )

    assert (
        "v155_user_session_policies"
        in tables
    )

    assert (
        conn.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]
        == 1
    )


def test_raw_session_secret_is_never_stored(conn):
    created = create_one(conn)

    row = conn.execute(
        """
        SELECT session_key_hash
        FROM v155_user_sessions
        WHERE id=?
        """,
        (
            created.session_row_id,
        ),
    ).fetchone()

    stored = row[0]

    assert (
        stored
        == hash_session_identifier(
            created.raw_session_id
        )
    )

    assert len(stored) == 64

    assert (
        created.raw_session_id
        != stored
    )

    all_text = "|".join(
        str(value)
        for value in conn.execute(
            """
            SELECT
                session_key_hash,
                login_ip,
                last_ip,
                user_agent,
                device_label
            FROM v155_user_sessions
            WHERE id=?
            """,
            (
                created.session_row_id,
            ),
        ).fetchone()
    )

    assert (
        created.raw_session_id
        not in all_text
    )


def test_default_limit_is_two_and_third_login_rejected(
    conn,
):
    first = create_one(conn)
    second = create_one(conn)

    assert (
        first.max_active_sessions
        == DEFAULT_MAX_ACTIVE_SESSIONS
        == 2
    )

    assert (
        second.max_active_sessions
        == 2
    )

    with pytest.raises(
        SessionLimitExceeded
    ):
        create_one(conn)

    active_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_user_sessions
        WHERE user_id=1
          AND status='active'
        """
    ).fetchone()[0]

    assert active_count == 2


def test_policy_limit_rejects_new_login_without_auto_kick(
    conn,
):
    set_max_active_sessions(
        conn,
        user_id=1,
        max_active_sessions=1,
        updated_by_user_id=2,
        now=utc(),
    )

    first = create_one(conn)

    with pytest.raises(
        SessionLimitExceeded
    ):
        create_one(conn)

    row = conn.execute(
        """
        SELECT status
        FROM v155_user_sessions
        WHERE id=?
        """,
        (
            first.session_row_id,
        ),
    ).fetchone()

    assert row[0] == "active"


def test_validation_fails_closed_for_wrong_identity_version_and_expiry(
    conn,
):
    now = utc()

    created = create_one(
        conn,
        now=now,
    )

    valid = validate_registered_session(
        conn,
        raw_session_id=(
            created.raw_session_id
        ),
        user_id=1,
        current_session_version=1,
        now=now,
    )

    assert valid.valid is True
    assert valid.reason == "ok"

    unknown = validate_registered_session(
        conn,
        raw_session_id="not-the-session",
        user_id=1,
        current_session_version=1,
        now=now,
    )

    assert unknown.valid is False
    assert unknown.reason == "not_found"

    wrong_user = validate_registered_session(
        conn,
        raw_session_id=(
            created.raw_session_id
        ),
        user_id=3,
        current_session_version=1,
        now=now,
    )

    assert wrong_user.valid is False
    assert (
        wrong_user.reason
        == "user_mismatch"
    )

    wrong_version = validate_registered_session(
        conn,
        raw_session_id=(
            created.raw_session_id
        ),
        user_id=1,
        current_session_version=2,
        now=now,
    )

    assert wrong_version.valid is False
    assert (
        wrong_version.reason
        == "session_version_mismatch"
    )

    expired = validate_registered_session(
        conn,
        raw_session_id=(
            created.raw_session_id
        ),
        user_id=1,
        current_session_version=1,
        now=(
            now
            + timedelta(hours=2)
        ),
    )

    assert expired.valid is False
    assert expired.reason == "expired"


def test_normal_logout_is_terminal_and_idempotent(
    conn,
):
    created = create_one(conn)

    changed = (
        mark_current_session_logged_out(
            conn,
            raw_session_id=(
                created.raw_session_id
            ),
            user_id=1,
            now=utc(),
        )
    )

    assert changed is True

    changed_again = (
        mark_current_session_logged_out(
            conn,
            raw_session_id=(
                created.raw_session_id
            ),
            user_id=1,
            now=utc(),
        )
    )

    assert changed_again is False

    result = validate_registered_session(
        conn,
        raw_session_id=(
            created.raw_session_id
        ),
        user_id=1,
        current_session_version=1,
        now=utc(),
    )

    assert result.valid is False
    assert result.reason == "not_active"
    assert result.status == "logged_out"


def test_single_session_revoke_does_not_bump_global_version(
    conn,
):
    first = create_one(conn)
    second = create_one(conn)

    before_version = conn.execute(
        """
        SELECT session_version
        FROM v158_users
        WHERE id=1
        """
    ).fetchone()[0]

    changed = revoke_session_by_id(
        conn,
        session_row_id=(
            first.session_row_id
        ),
        target_user_id=1,
        actor_user_id=2,
        reason="admin_test",
        now=utc(),
    )

    assert changed is True

    after_version = conn.execute(
        """
        SELECT session_version
        FROM v158_users
        WHERE id=1
        """
    ).fetchone()[0]

    assert after_version == before_version

    rows = {
        row["id"]: row["status"]
        for row in conn.execute(
            """
            SELECT id, status
            FROM v155_user_sessions
            WHERE user_id=1
            """
        )
    }

    assert (
        rows[first.session_row_id]
        == "revoked"
    )

    assert (
        rows[second.session_row_id]
        == "active"
    )

    changed_again = revoke_session_by_id(
        conn,
        session_row_id=(
            first.session_row_id
        ),
        target_user_id=1,
        actor_user_id=2,
        reason="admin_test",
        now=utc(),
    )

    assert changed_again is False


def test_registry_all_revoke_is_separate_from_version_bump(
    conn,
):
    create_one(conn)
    create_one(conn)

    before_version = conn.execute(
        """
        SELECT session_version
        FROM v158_users
        WHERE id=1
        """
    ).fetchone()[0]

    count = revoke_all_registry_sessions(
        conn,
        user_id=1,
        actor_user_id=2,
        reason="account_invalidation_test",
        now=utc(),
    )

    assert count == 2

    after_version = conn.execute(
        """
        SELECT session_version
        FROM v158_users
        WHERE id=1
        """
    ).fetchone()[0]

    assert after_version == before_version

    active = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_user_sessions
        WHERE user_id=1
          AND status='active'
        """
    ).fetchone()[0]

    assert active == 0


def test_old_version_rows_do_not_consume_new_version_slots(
    conn,
):
    create_one(conn)
    create_one(conn)

    conn.execute(
        """
        UPDATE v158_users
        SET session_version=2
        WHERE id=1
        """
    )

    conn.commit()

    first_new = create_one(
        conn,
        session_version=2,
    )

    second_new = create_one(
        conn,
        session_version=2,
    )

    assert first_new.session_row_id
    assert second_new.session_row_id


def test_last_seen_update_is_throttled(
    conn,
):
    start = utc()

    created = create_one(
        conn,
        now=start,
    )

    too_soon = touch_registered_session(
        conn,
        raw_session_id=(
            created.raw_session_id
        ),
        user_id=1,
        last_ip="10.0.0.2",
        now=(
            start
            + timedelta(seconds=60)
        ),
    )

    assert too_soon is False

    later = touch_registered_session(
        conn,
        raw_session_id=(
            created.raw_session_id
        ),
        user_id=1,
        last_ip="10.0.0.3",
        now=(
            start
            + timedelta(seconds=301)
        ),
    )

    assert later is True

    row = conn.execute(
        """
        SELECT last_ip
        FROM v155_user_sessions
        WHERE id=?
        """,
        (
            created.session_row_id,
        ),
    ).fetchone()

    assert row[0] == "10.0.0.3"


def test_nested_write_transaction_is_rejected(
    conn,
):
    conn.execute("BEGIN")

    try:
        with pytest.raises(
            TransactionOwnershipError
        ):
            create_one(conn)

    finally:
        conn.rollback()


def test_mutation_fails_closed_when_foreign_keys_disabled(
    conn,
):
    conn.commit()

    conn.execute(
        "PRAGMA foreign_keys=OFF"
    )

    assert (
        conn.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]
        == 0
    )

    with pytest.raises(
        ForeignKeysRequired
    ):
        create_one(conn)

    conn.execute(
        "PRAGMA foreign_keys=ON"
    )


def test_session_listing_contains_metadata_but_not_raw_secret(
    conn,
):
    created = create_one(conn)

    rows = list_user_sessions(
        conn,
        user_id=1,
    )

    assert len(rows) == 1

    row = rows[0]

    assert row["id"] == (
        created.session_row_id
    )

    assert row["status"] == "active"
    assert row["login_ip"] == "10.0.0.1"

    assert (
        "session_key_hash"
        not in row
    )

    assert (
        created.raw_session_id
        not in repr(row)
    )



def test_idle_timeout_terminalization_marks_expired_and_is_idempotent(
    conn,
):
    from services.v155_session_registry_service import (
        mark_current_session_expired,
    )

    first = create_one(conn)

    before_version = int(
        conn.execute(
            """
            SELECT session_version
            FROM v155_user_sessions
            WHERE id=?
            """,
            (
                first.session_row_id,
            ),
        ).fetchone()[0]
    )

    changed = (
        mark_current_session_expired(
            conn,
            raw_session_id=(
                first.raw_session_id
            ),
            user_id=1,
        )
    )

    assert changed is True

    row = conn.execute(
        """
        SELECT
            status,
            session_version,
            revoked_at,
            revoke_reason,
            revoked_by_user_id
        FROM v155_user_sessions
        WHERE id=?
        """,
        (
            first.session_row_id,
        ),
    ).fetchone()

    assert row[0] == "expired"
    assert int(row[1]) == before_version
    assert row[2]
    assert row[3] == "idle_timeout"
    assert row[4] is None

    changed_again = (
        mark_current_session_expired(
            conn,
            raw_session_id=(
                first.raw_session_id
            ),
            user_id=1,
        )
    )

    assert changed_again is False

    row_again = conn.execute(
        """
        SELECT
            status,
            session_version,
            revoke_reason,
            revoked_by_user_id
        FROM v155_user_sessions
        WHERE id=?
        """,
        (
            first.session_row_id,
        ),
    ).fetchone()

    assert tuple(row_again) == (
        "expired",
        before_version,
        "idle_timeout",
        None,
    )


def test_idle_timeout_expired_row_releases_concurrent_capacity(
    conn,
):
    from services.v155_session_registry_service import (
        mark_current_session_expired,
    )

    first = create_one(conn)

    assert (
        mark_current_session_expired(
            conn,
            raw_session_id=(
                first.raw_session_id
            ),
            user_id=1,
        )
        is True
    )

    second = create_one(conn)
    third = create_one(conn)

    assert second.max_active_sessions == 2
    assert third.max_active_sessions == 2

    active_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM v155_user_sessions
            WHERE user_id=1
              AND status='active'
            """
        ).fetchone()[0]
    )

    assert active_count == 2

    with pytest.raises(
        SessionLimitExceeded
    ):
        create_one(conn)
