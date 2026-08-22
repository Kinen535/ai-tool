from __future__ import annotations

import sqlite3
from typing import Any


ACCOUNT_ROLE_TO_WORKSPACE_ROLE = {
    "super_admin": "workspace_admin",
    "manager": "manager",
    "viewer": "viewer",
}


def ensure_default_workspace_membership(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    account_role: str,
) -> dict[str, Any]:

    user_id = int(user_id)

    workspace_role = (
        ACCOUNT_ROLE_TO_WORKSPACE_ROLE.get(
            str(account_role or "").strip()
        )
    )

    if not workspace_role:
        raise ValueError(
            "unsupported account role"
        )

    workspaces = conn.execute(
        """
        SELECT
            id
        FROM v155_workspaces
        WHERE status='active'
        ORDER BY id
        LIMIT 2
        """
    ).fetchall()

    if len(workspaces) != 1:
        raise RuntimeError(
            "active workspace count must be exactly one"
        )

    workspace_id = int(
        workspaces[0]["id"]
    )


    role = conn.execute(
        """
        SELECT
            id
        FROM v155_roles
        WHERE workspace_id=?
          AND role_key=?
          AND status='active'
        LIMIT 1
        """,
        (
            workspace_id,
            workspace_role,
        ),
    ).fetchone()

    if not role:
        raise RuntimeError(
            "workspace role missing"
        )

    role_id = int(
        role["id"]
    )

    existing = conn.execute(
        """
        SELECT
            id
        FROM v155_workspace_members
        WHERE workspace_id=?
          AND user_id=?
        LIMIT 1
        """,
        (
            workspace_id,
            user_id,
        ),
    ).fetchone()


    if existing:
        return {
            "ok": True,
            "created": False,
            "workspace_id": workspace_id,
            "role_id": role_id,
        }


    conn.execute(
        """
        INSERT INTO v155_workspace_members
        (
            workspace_id,
            user_id,
            role_id,
            status,
            is_default
        )
        VALUES
        (
            ?,
            ?,
            ?,
            'active',
            1
        )
        """,
        (
            workspace_id,
            user_id,
            role_id,
        ),
    )


    return {
        "ok": True,
        "created": True,
        "workspace_id": workspace_id,
        "role_id": role_id,
    }
