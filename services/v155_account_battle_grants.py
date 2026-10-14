
from __future__ import annotations
import sqlite3

class BattleGrantDenied(Exception):
    pass

def set_membership_battle_grants(
    conn: sqlite3.Connection, *,
    workspace_id: int,
    membership_id: int,
    battle_ids,
    default_battle_id: int,
):
    """Replace one membership's active grant set atomically.

    The HTTP caller must independently check admin authority and CSRF.
    Requires a caller-owned BEGIN IMMEDIATE transaction.
    """
    try:
        wid = int(workspace_id)
        mid = int(membership_id)
        default = int(default_battle_id)
        ids = tuple(int(x) for x in battle_ids)
    except (TypeError, ValueError) as exc:
        raise BattleGrantDenied("invalid_identifiers") from exc

    if (wid <= 0 or mid <= 0 or not ids
            or any(x <= 0 for x in ids)
            or len(ids) != len(set(ids))
            or default not in ids):
        raise BattleGrantDenied("invalid_grant_set")

    if not conn.in_transaction:
        raise BattleGrantDenied("transaction_required")

    conn.execute("SAVEPOINT admin_battle_grants")
    try:
        member = conn.execute("""
            SELECT m.id
            FROM v155_workspace_members m
            JOIN v158_users u ON u.id=m.user_id
            JOIN v155_workspaces w ON w.id=m.workspace_id
            JOIN v155_roles r
              ON r.id=m.role_id AND r.workspace_id=m.workspace_id
            WHERE m.id=? AND m.workspace_id=?
              AND m.status='active'
              AND u.status='active'
              AND w.status='active'
              AND r.status='active'
        """, (mid, wid)).fetchone()

        if member is None:
            raise BattleGrantDenied("invalid_membership")

        valid = {
            int(row[0]) for row in conn.execute("""
                SELECT wb.battle_id
                FROM v155_workspace_battles wb
                JOIN battles b ON b.id=wb.battle_id
                WHERE wb.workspace_id=? AND wb.status='active'
            """, (wid,))
        }
        if not set(ids).issubset(valid):
            raise BattleGrantDenied("battle_outside_workspace")

        # Clear the old default first to respect the partial unique index.
        conn.execute("""
            UPDATE v155_membership_battle_access
            SET is_default=0
            WHERE membership_id=? AND is_default=1
        """, (mid,))

        for bid in ids:
            conn.execute("""
                INSERT INTO v155_membership_battle_access
                    (membership_id,battle_id,status,is_default)
                VALUES (?,?,'active',0)
                ON CONFLICT(membership_id,battle_id)
                DO UPDATE SET status='active',is_default=0
            """, (mid,bid))

        placeholders = ",".join("?" for _ in ids)
        conn.execute(f"""
            UPDATE v155_membership_battle_access
            SET status='revoked',is_default=0
            WHERE membership_id=?
              AND battle_id NOT IN ({placeholders})
        """, (mid,*ids))

        cursor = conn.execute("""
            UPDATE v155_membership_battle_access
            SET is_default=1
            WHERE membership_id=? AND battle_id=? AND status='active'
        """, (mid,default))
        if cursor.rowcount != 1:
            raise BattleGrantDenied("default_update_failed")

        actual = conn.execute("""
            SELECT battle_id,is_default
            FROM v155_membership_battle_access
            WHERE membership_id=? AND status='active'
        """, (mid,)).fetchall()
        found = {int(row[0]) for row in actual}
        defaults = [int(row[0]) for row in actual if row[1] == 1]
        if found != set(ids) or defaults != [default]:
            raise BattleGrantDenied("grant_verification_failed")

        conn.execute("RELEASE SAVEPOINT admin_battle_grants")
        return {"battle_ids":tuple(sorted(found)),
                "current_battle_id":default}

    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT admin_battle_grants")
        conn.execute("RELEASE SAVEPOINT admin_battle_grants")
        raise
