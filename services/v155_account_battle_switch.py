
from __future__ import annotations

import sqlite3

from services.v155_account_battle_scope import (
    resolve_account_battle_scope,
)


class AccountBattleSwitchDenied(Exception):
    pass


def switch_account_battle(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    membership_id: int,
    workspace_id: int,
    target_battle_id: int,
) -> dict:
    """Switch one account's default authorized battle.

    Requires a caller-owned write transaction, preferably BEGIN IMMEDIATE.
    Never changes workspace/global is_current values.
    The HTTP caller must independently enforce login, CSRF and permissions.
    """
    try:
        uid = int(user_id)
        mid = int(membership_id)
        wid = int(workspace_id)
        bid = int(target_battle_id)
    except (TypeError, ValueError) as exc:
        raise AccountBattleSwitchDenied("invalid_identifiers") from exc

    if min(uid, mid, wid, bid) <= 0:
        raise AccountBattleSwitchDenied("invalid_identifiers")

    if not conn.in_transaction:
        raise AccountBattleSwitchDenied("write_transaction_required")

    conn.execute("SAVEPOINT a2_account_battle_switch")
    try:
        owner = conn.execute("""
            SELECT m.id
            FROM v155_workspace_members AS m
            JOIN v158_users AS u ON u.id=m.user_id
            JOIN v155_workspaces AS w ON w.id=m.workspace_id
            JOIN v155_roles AS r
              ON r.id=m.role_id AND r.workspace_id=m.workspace_id
            WHERE m.id=? AND m.user_id=? AND m.workspace_id=?
              AND m.status='active'
              AND m.is_default=1
              AND u.status='active'
              AND w.status='active'
              AND r.status='active'
        """, (mid, uid, wid)).fetchone()

        if owner is None:
            raise AccountBattleSwitchDenied("membership_not_owned_or_active")

        scope = resolve_account_battle_scope(
            conn, membership_id=mid, workspace_id=wid
        )
        if scope is None or bid not in scope["battle_ids"]:
            raise AccountBattleSwitchDenied("battle_not_authorized")

        conn.execute("""
            UPDATE v155_membership_battle_access
            SET is_default=0
            WHERE membership_id=?
              AND is_default=1
        """, (mid,))

        result = conn.execute("""
            UPDATE v155_membership_battle_access
            SET is_default=1
            WHERE membership_id=? AND battle_id=?
              AND status='active'
        """, (mid, bid))

        if result.rowcount != 1:
            raise AccountBattleSwitchDenied("target_update_failed")

        updated = resolve_account_battle_scope(
            conn, membership_id=mid, workspace_id=wid
        )
        if updated is None or updated["current_battle_id"] != bid:
            raise AccountBattleSwitchDenied("post_switch_scope_invalid")

        conn.execute("RELEASE SAVEPOINT a2_account_battle_switch")
        return updated

    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT a2_account_battle_switch")
        conn.execute("RELEASE SAVEPOINT a2_account_battle_switch")
        raise
