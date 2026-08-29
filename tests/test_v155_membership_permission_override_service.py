from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

import services.v155_membership_permission_override_service as service
from services.v155_rbac_workspace_resolver import (
    resolve_default_access_context,
)


PLATFORM_ONLY = {
    "account.manage",
    "security.manage",
}


def _backup_database(
    source: Path,
    destination: Path,
) -> None:
    src = sqlite3.connect(
        str(source),
        timeout=15,
    )

    try:
        dst = sqlite3.connect(
            str(destination),
            timeout=15,
        )

        try:
            src.backup(dst)
        finally:
            dst.close()

    finally:
        src.close()


@pytest.fixture
def conn(tmp_path):
    seed_value = os.environ.get(
        "V155_OVERRIDE_TEST_SEED_DB",
        "",
    )

    assert seed_value, (
        "V155_OVERRIDE_TEST_SEED_DB is required"
    )

    seed = Path(seed_value).resolve()

    assert seed.is_file()

    test_db = (
        tmp_path
        / "override_test.sqlite3"
    )

    _backup_database(
        seed,
        test_db,
    )

    db = sqlite3.connect(
        str(test_db),
        timeout=15,
    )

    db.row_factory = sqlite3.Row
    db.execute(
        "PRAGMA foreign_keys=ON"
    )

    try:
        yield db

    finally:
        try:
            if db.in_transaction:
                db.rollback()

            assert (
                db.execute(
                    "PRAGMA quick_check"
                ).fetchone()[0]
                == "ok"
            )

            assert (
                db.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
                == []
            )

        finally:
            db.close()

            for cleanup_path in (
                test_db,
                Path(str(test_db) + "-journal"),
                Path(str(test_db) + "-wal"),
                Path(str(test_db) + "-shm"),
            ):
                cleanup_path.unlink(
                    missing_ok=True
                )


def _fixture_state(conn):
    actor = conn.execute(
        """
        SELECT id
        FROM v158_users
        WHERE role='super_admin'
          AND status='active'
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()

    assert actor is not None

    target = conn.execute(
        """
        SELECT
            wm.id AS membership_id,
            wm.workspace_id,
            wm.user_id,
            wm.role_id
        FROM v155_workspace_members wm
        JOIN v158_users u
          ON u.id=wm.user_id
        JOIN v155_workspaces w
          ON w.id=wm.workspace_id
        JOIN v155_roles r
          ON r.id=wm.role_id
         AND r.workspace_id=wm.workspace_id
        WHERE wm.status='active'
          AND wm.is_default=1
          AND u.status='active'
          AND w.status='active'
          AND r.status='active'
          AND r.role_key='viewer'
        ORDER BY wm.id
        LIMIT 1
        """
    ).fetchone()

    assert target is not None

    peer = conn.execute(
        """
        SELECT
            wm.id AS membership_id,
            wm.user_id
        FROM v155_workspace_members wm
        JOIN v158_users u
          ON u.id=wm.user_id
        JOIN v155_roles r
          ON r.id=wm.role_id
         AND r.workspace_id=wm.workspace_id
        WHERE wm.status='active'
          AND wm.is_default=1
          AND u.status='active'
          AND r.status='active'
          AND r.role_key='viewer'
          AND wm.id<>?
        ORDER BY wm.id
        LIMIT 1
        """,
        (
            int(target["membership_id"]),
        ),
    ).fetchone()

    assert peer is not None

    baseline = {
        str(row["permission_key"])
        for row in conn.execute(
            """
            SELECT p.permission_key
            FROM v155_role_permissions rp
            JOIN v155_permissions p
              ON p.id=rp.permission_id
            WHERE rp.role_id=?
            """,
            (
                int(target["role_id"]),
            ),
        ).fetchall()
    } - PLATFORM_ONLY

    grantable = {
        str(row["permission_key"])
        for row in conn.execute(
            """
            SELECT DISTINCT p.permission_key
            FROM v155_roles r
            JOIN v155_role_permissions rp
              ON rp.role_id=r.id
            JOIN v155_permissions p
              ON p.id=rp.permission_id
            WHERE r.workspace_id=?
              AND r.status='active'
            """,
            (
                int(target["workspace_id"]),
            ),
        ).fetchall()
    } - PLATFORM_ONLY

    grant_candidates = sorted(
        grantable - baseline
    )

    assert grant_candidates

    deny_candidates = sorted(
        baseline & grantable
    )

    assert deny_candidates

    nongrantable = [
        str(row["permission_key"])
        for row in conn.execute(
            """
            SELECT permission_key
            FROM v155_permissions
            ORDER BY permission_key
            """
        ).fetchall()
        if (
            str(row["permission_key"])
            not in grantable
            and str(row["permission_key"])
            not in PLATFORM_ONLY
        )
    ]

    assert nongrantable

    return {
        "actor_id": int(actor["id"]),
        "membership_id": int(
            target["membership_id"]
        ),
        "workspace_id": int(
            target["workspace_id"]
        ),
        "user_id": int(
            target["user_id"]
        ),
        "role_id": int(
            target["role_id"]
        ),
        "peer_membership_id": int(
            peer["membership_id"]
        ),
        "peer_user_id": int(
            peer["user_id"]
        ),
        "grant_key": grant_candidates[0],
        "deny_key": deny_candidates[0],
        "nongrantable_key": nongrantable[0],
    }


def _override(
    conn,
    membership_id,
    permission_key,
):
    return conn.execute(
        """
        SELECT
            o.effect,
            o.created_at,
            o.updated_at
        FROM v155_membership_permission_overrides o
        JOIN v155_permissions p
          ON p.id=o.permission_id
        WHERE o.membership_id=?
          AND p.permission_key=?
        """,
        (
            membership_id,
            permission_key,
        ),
    ).fetchone()


def _audit_rows(
    conn,
    action_key,
):
    return conn.execute(
        """
        SELECT *
        FROM v158_action_logs
        WHERE action_key=?
        ORDER BY id
        """,
        (
            action_key,
        ),
    ).fetchall()


def test_valid_grant_and_resolver_integration(conn):
    state = _fixture_state(conn)

    result = (
        service.set_membership_permission_override(
            conn,
            actor_user_id=state["actor_id"],
            target_membership_id=state["membership_id"],
            permission_key=state["grant_key"],
            effect="grant",
            audit={
                "request_method": "POST",
                "request_path": "/test/grant",
            },
        )
    )

    assert result["ok"] is True
    assert result["code"] == "override_set"
    assert result["changed"] is True
    assert result["after_effect"] == "grant"

    row = _override(
        conn,
        state["membership_id"],
        state["grant_key"],
    )

    assert row is not None
    assert row["effect"] == "grant"

    context = resolve_default_access_context(
        conn,
        state["user_id"],
    )

    assert context is not None
    assert (
        state["grant_key"]
        in context["permissions"]
    )

    audits = _audit_rows(
        conn,
        "membership_permission_grant",
    )

    assert audits
    assert (
        audits[-1]["target_type"]
        == "workspace_membership_permission"
    )
    assert (
        audits[-1]["result_status"]
        == "success"
    )


def test_valid_deny_and_deny_precedence(conn):
    state = _fixture_state(conn)

    result = (
        service.set_membership_permission_override(
            conn,
            actor_user_id=state["actor_id"],
            target_membership_id=state["membership_id"],
            permission_key=state["deny_key"],
            effect="deny",
        )
    )

    assert result["ok"] is True
    assert result["after_effect"] == "deny"

    context = resolve_default_access_context(
        conn,
        state["user_id"],
    )

    assert context is not None
    assert (
        state["deny_key"]
        not in context["permissions"]
    )


def test_effect_transitions_and_idempotency(conn):
    state = _fixture_state(conn)
    key = state["grant_key"]

    first = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=key,
        effect="grant",
    )

    assert first["code"] == "override_set"

    row1 = _override(
        conn,
        state["membership_id"],
        key,
    )

    assert row1 is not None

    created_at = row1["created_at"]

    permission_id = conn.execute(
        """
        SELECT id
        FROM v155_permissions
        WHERE permission_key=?
        """,
        (key,),
    ).fetchone()[0]

    conn.execute(
        """
        UPDATE v155_membership_permission_overrides
        SET updated_at='2000-01-01 00:00:00'
        WHERE membership_id=?
          AND permission_id=?
        """,
        (
            state["membership_id"],
            permission_id,
        ),
    )
    conn.commit()

    second = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=key,
        effect="deny",
    )

    assert second["ok"] is True
    assert second["changed"] is True

    row2 = _override(
        conn,
        state["membership_id"],
        key,
    )

    assert row2["effect"] == "deny"
    assert row2["created_at"] == created_at
    assert (
        row2["updated_at"]
        != "2000-01-01 00:00:00"
    )

    third = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=key,
        effect="deny",
    )

    assert third["ok"] is True
    assert third["code"] == "override_unchanged"
    assert third["changed"] is False

    count = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_membership_permission_overrides
        WHERE membership_id=?
          AND permission_id=?
        """,
        (
            state["membership_id"],
            permission_id,
        ),
    ).fetchone()[0]

    assert count == 1

    fourth = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=key,
        effect="grant",
    )

    assert fourth["ok"] is True
    assert fourth["changed"] is True


def test_clear_existing_and_missing_are_idempotent(conn):
    state = _fixture_state(conn)

    service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    cleared = (
        service.clear_membership_permission_override(
            conn,
            actor_user_id=state["actor_id"],
            target_membership_id=state["membership_id"],
            permission_key=state["grant_key"],
        )
    )

    assert cleared["ok"] is True
    assert cleared["code"] == "override_cleared"
    assert cleared["changed"] is True

    assert _override(
        conn,
        state["membership_id"],
        state["grant_key"],
    ) is None

    again = (
        service.clear_membership_permission_override(
            conn,
            actor_user_id=state["actor_id"],
            target_membership_id=state["membership_id"],
            permission_key=state["grant_key"],
        )
    )

    assert again["ok"] is True
    assert (
        again["code"]
        == "override_already_clear"
    )
    assert again["changed"] is False


@pytest.mark.parametrize(
    "permission_key",
    [
        "account.manage",
        "security.manage",
    ],
)
def test_platform_permissions_blocked(
    conn,
    permission_key,
):
    state = _fixture_state(conn)

    result = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=permission_key,
        effect="grant",
    )

    assert result["ok"] is False
    assert (
        result["code"]
        == "platform_permission_forbidden"
    )

    assert _override(
        conn,
        state["membership_id"],
        permission_key,
    ) is None


def test_non_workspace_grantable_permission_blocked(conn):
    state = _fixture_state(conn)

    result = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["nongrantable_key"],
        effect="grant",
    )

    assert result["ok"] is False
    assert (
        result["code"]
        == "permission_not_grantable"
    )


def test_membership_isolation(conn):
    state = _fixture_state(conn)

    before_peer = resolve_default_access_context(
        conn,
        state["peer_user_id"],
    )

    assert before_peer is not None

    result = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    assert result["ok"] is True

    peer_override = _override(
        conn,
        state["peer_membership_id"],
        state["grant_key"],
    )

    assert peer_override is None

    after_peer = resolve_default_access_context(
        conn,
        state["peer_user_id"],
    )

    assert after_peer == before_peer


def test_missing_and_non_super_admin_actor_blocked(conn):
    state = _fixture_state(conn)

    missing = service.set_membership_permission_override(
        conn,
        actor_user_id=999999999,
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    assert missing["ok"] is False
    assert missing["code"] == "actor_missing"

    viewer = service.set_membership_permission_override(
        conn,
        actor_user_id=state["user_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    assert viewer["ok"] is False
    assert viewer["code"] == "forbidden"


def test_disabled_actor_blocked(conn):
    state = _fixture_state(conn)

    conn.execute(
        """
        UPDATE v158_users
        SET status='disabled'
        WHERE id=?
        """,
        (
            state["actor_id"],
        ),
    )
    conn.commit()

    result = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    assert result["ok"] is False
    assert result["code"] == "actor_disabled"


@pytest.mark.parametrize(
    "dimension",
    [
        "membership",
        "user",
        "workspace",
        "role",
    ],
)
def test_inactive_target_dimensions_blocked(
    conn,
    dimension,
):
    state = _fixture_state(conn)

    if dimension == "membership":
        conn.execute(
            """
            UPDATE v155_workspace_members
            SET status='disabled'
            WHERE id=?
            """,
            (
                state["membership_id"],
            ),
        )

    elif dimension == "user":
        conn.execute(
            """
            UPDATE v158_users
            SET status='disabled'
            WHERE id=?
            """,
            (
                state["user_id"],
            ),
        )

    elif dimension == "workspace":
        conn.execute(
            """
            UPDATE v155_workspaces
            SET status='disabled'
            WHERE id=?
            """,
            (
                state["workspace_id"],
            ),
        )

    else:
        conn.execute(
            """
            UPDATE v155_roles
            SET status='disabled'
            WHERE id=?
            """,
            (
                state["role_id"],
            ),
        )

    conn.commit()

    result = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    assert result["ok"] is False
    assert (
        result["code"]
        == "membership_unavailable"
    )


def test_invalid_membership_effect_and_permission(conn):
    state = _fixture_state(conn)

    invalid_membership = (
        service.set_membership_permission_override(
            conn,
            actor_user_id=state["actor_id"],
            target_membership_id=0,
            permission_key=state["grant_key"],
            effect="grant",
        )
    )

    assert (
        invalid_membership["code"]
        == "invalid_membership"
    )

    invalid_effect = (
        service.set_membership_permission_override(
            conn,
            actor_user_id=state["actor_id"],
            target_membership_id=state["membership_id"],
            permission_key=state["grant_key"],
            effect="corrupt",
        )
    )

    assert invalid_effect["code"] == "invalid_effect"

    missing_permission = (
        service.set_membership_permission_override(
            conn,
            actor_user_id=state["actor_id"],
            target_membership_id=state["membership_id"],
            permission_key="does.not.exist",
            effect="grant",
        )
    )

    assert (
        missing_permission["code"]
        == "permission_missing"
    )


def test_external_transaction_rejected(conn):
    state = _fixture_state(conn)

    conn.execute("BEGIN")

    result = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    assert result["ok"] is False
    assert (
        result["code"]
        == "external_transaction"
    )
    assert result["audit_written"] is False
    assert conn.in_transaction is True

    conn.rollback()

    assert _override(
        conn,
        state["membership_id"],
        state["grant_key"],
    ) is None


def test_success_audit_failure_rolls_mutation_back(
    conn,
    monkeypatch,
):
    state = _fixture_state(conn)

    before_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_membership_permission_overrides
        """
    ).fetchone()[0]

    def explode(*args, **kwargs):
        raise RuntimeError(
            "injected audit failure"
        )

    monkeypatch.setattr(
        service,
        "record_action_log",
        explode,
    )

    result = service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    assert result["ok"] is False
    assert result["code"] == "internal_error"
    assert result["audit_written"] is False

    after_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_membership_permission_overrides
        """
    ).fetchone()[0]

    assert after_count == before_count

    assert _override(
        conn,
        state["membership_id"],
        state["grant_key"],
    ) is None


def test_session_version_unchanged(conn):
    state = _fixture_state(conn)

    before = conn.execute(
        """
        SELECT session_version
        FROM v158_users
        WHERE id=?
        """,
        (
            state["user_id"],
        ),
    ).fetchone()[0]

    service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    service.set_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="deny",
    )

    service.clear_membership_permission_override(
        conn,
        actor_user_id=state["actor_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
    )

    after = conn.execute(
        """
        SELECT session_version
        FROM v158_users
        WHERE id=?
        """,
        (
            state["user_id"],
        ),
    ).fetchone()[0]

    assert after == before


def test_read_model_and_stale_override_clearable(conn):
    state = _fixture_state(conn)

    permission = conn.execute(
        """
        SELECT id
        FROM v155_permissions
        WHERE permission_key='account.manage'
        """
    ).fetchone()

    assert permission is not None

    conn.execute(
        """
        INSERT INTO v155_membership_permission_overrides(
            membership_id,
            permission_id,
            effect
        )
        VALUES (?, ?, 'grant')
        """,
        (
            state["membership_id"],
            int(permission["id"]),
        ),
    )
    conn.commit()

    report = (
        service.get_membership_permission_admin_state(
            conn,
            target_membership_id=state["membership_id"],
        )
    )

    assert report["ok"] is True

    stale = [
        row
        for row in report["stored_overrides"]
        if (
            row["permission_key"]
            == "account.manage"
        )
    ]

    assert len(stale) == 1
    assert stale[0]["stale"] is True
    assert stale[0]["platform_only"] is True

    result = (
        service.clear_membership_permission_override(
            conn,
            actor_user_id=state["actor_id"],
            target_membership_id=state["membership_id"],
            permission_key="account.manage",
        )
    )

    assert result["ok"] is True
    assert result["code"] == "override_cleared"

    assert _override(
        conn,
        state["membership_id"],
        "account.manage",
    ) is None


@pytest.mark.parametrize(
    "actor_value",
    [
        None,
        "",
        "not-an-id",
    ],
)
def test_invalid_actor_scalar_never_escapes_public_api(
    conn,
    actor_value,
):
    state = _fixture_state(conn)

    result = service.set_membership_permission_override(
        conn,
        actor_user_id=actor_value,
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    assert isinstance(result, dict)
    assert result["ok"] is False


def test_failure_audit_written_for_blocked_operation(conn):
    state = _fixture_state(conn)

    before = conn.execute(
        """
        SELECT COUNT(*)
        FROM v158_action_logs
        """
    ).fetchone()[0]

    result = service.set_membership_permission_override(
        conn,
        actor_user_id=state["user_id"],
        target_membership_id=state["membership_id"],
        permission_key=state["grant_key"],
        effect="grant",
    )

    assert result["ok"] is False
    assert result["audit_written"] is True

    after = conn.execute(
        """
        SELECT COUNT(*)
        FROM v158_action_logs
        """
    ).fetchone()[0]

    assert after == before + 1

    row = conn.execute(
        """
        SELECT
            action_key,
            result_status,
            target_type
        FROM v158_action_logs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    assert row is not None
    assert row["result_status"] == "blocked"
    assert (
        row["target_type"]
        == "workspace_membership_permission"
    )
