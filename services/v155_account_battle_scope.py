from __future__ import annotations

import sqlite3


def resolve_account_battle_scope(
    conn: sqlite3.Connection,
    *,
    membership_id: int,
    workspace_id: int,
    workspace_current_battle_id: int | None = None,
) -> dict | None:
    """Resolve effective, account-specific battle authorization.

    No grant, missing schema, inconsistent default, or SQL error:
    fail closed. Caller must not fall back to Workspace battle list.
    """
    try:
        mid = int(membership_id)
        wid = int(workspace_id)
        if mid <= 0 or wid <= 0:
            return None

        rows = conn.execute("""
            SELECT
                a.battle_id,
                a.is_default
            FROM v155_membership_battle_access a
            JOIN v155_workspace_members m
              ON m.id=a.membership_id
            JOIN v158_users u
              ON u.id=m.user_id
            JOIN v155_workspaces w
              ON w.id=m.workspace_id
            JOIN v155_roles r
              ON r.id=m.role_id
             AND r.workspace_id=m.workspace_id
            JOIN v155_workspace_battles wb
              ON wb.workspace_id=m.workspace_id
             AND wb.battle_id=a.battle_id
            WHERE a.membership_id=?
              AND m.workspace_id=?
              AND a.status='active'
              AND u.status='active'
              AND m.status='active'
              AND w.status='active'
              AND r.status='active'
              AND wb.status='active'
            ORDER BY a.battle_id
        """, (mid, wid)).fetchall()

        if not rows:
            return None

        ids = tuple(int(row[0]) for row in rows)
        if any(bid <= 0 for bid in ids) or len(set(ids)) != len(ids):
            return None

        defaults = [
            int(row[0]) for row in rows if int(row[1]) == 1
        ]
        if len(defaults) > 1:
            return None

        if defaults:
            current = defaults[0]
        elif len(ids) == 1:
            current = ids[0]
        else:
            # Multiple grants without a default require
            # explicit user selection in the future.
            return None

        return {
            "battle_ids": ids,
            "current_battle_id": current,
        }

    except (sqlite3.Error, TypeError, ValueError, IndexError):
        return None
