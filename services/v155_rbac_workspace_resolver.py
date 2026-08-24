from __future__ import annotations

import sqlite3
from typing import Any


PLATFORM_ONLY_PERMISSIONS = frozenset(
    {
        "account.manage",
        "security.manage",
    }
)


def resolve_default_access_context(
    conn: sqlite3.Connection,
    user_id: int,
) -> dict[str, Any] | None:
    """
    Resolve one user's active default Workspace context.

    Fail closed:
    - user must exist and be active
    - exactly one active default membership must resolve
    - workspace must be active
    - role must be active
    - role must belong to the same workspace
    - multiple current battles are rejected

    This resolver performs SELECT statements only.
    It does not grant platform-only permissions through Workspace RBAC.
    """

    try:
        user_id_value = int(
            user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if user_id_value <= 0:
        return None

    rows = conn.execute(
        """
        SELECT
            u.id AS user_id,
            u.username,
            u.display_name,
            u.role AS legacy_role,
            u.status AS user_status,

            wm.id AS membership_id,
            wm.workspace_id,
            wm.role_id,
            wm.status AS membership_status,
            wm.is_default,

            w.workspace_key,
            w.workspace_name,
            w.status AS workspace_status,

            r.role_key AS workspace_role,
            r.role_name,
            r.status AS role_status

        FROM v158_users AS u

        JOIN v155_workspace_members AS wm
          ON wm.user_id=u.id

        JOIN v155_workspaces AS w
          ON w.id=wm.workspace_id

        JOIN v155_roles AS r
          ON r.id=wm.role_id
         AND r.workspace_id=wm.workspace_id

        WHERE u.id=?
          AND u.status='active'
          AND wm.status='active'
          AND wm.is_default=1
          AND w.status='active'
          AND r.status='active'

        ORDER BY wm.id
        LIMIT 2
        """,
        (
            user_id_value,
        ),
    ).fetchall()

    if len(rows) != 1:
        return None

    row = rows[0]

    workspace_id = int(
        row["workspace_id"]
    )

    role_id = int(
        row["role_id"]
    )

    permission_rows = conn.execute(
        """
        SELECT
            p.permission_key

        FROM v155_role_permissions AS rp

        JOIN v155_permissions AS p
          ON p.id=rp.permission_id

        WHERE rp.role_id=?

        ORDER BY p.permission_key
        """,
        (
            role_id,
        ),
    ).fetchall()

    permissions = frozenset(
        str(
            permission_row[
                "permission_key"
            ]
        )
        for permission_row
        in permission_rows
        if permission_row[
            "permission_key"
        ]
    )

    # Workspace RBAC must never implicitly grant
    # platform bootstrap/admin permissions.
    permissions = frozenset(
        permission
        for permission in permissions
        if permission
        not in PLATFORM_ONLY_PERMISSIONS
    )

    battle_rows = conn.execute(
        """
        SELECT
            wb.battle_id,
            wb.is_current,
            wb.status,
            b.battle_name

        FROM v155_workspace_battles AS wb

        JOIN battles AS b
          ON b.id=wb.battle_id

        WHERE wb.workspace_id=?
          AND wb.status='active'

        ORDER BY wb.battle_id
        """,
        (
            workspace_id,
        ),
    ).fetchall()

    battle_ids = tuple(
        int(
            battle_row[
                "battle_id"
            ]
        )
        for battle_row
        in battle_rows
    )

    current_battle_ids = tuple(
        int(
            battle_row[
                "battle_id"
            ]
        )
        for battle_row
        in battle_rows
        if int(
            battle_row[
                "is_current"
            ]
            or 0
        ) == 1
    )

    # Defensive fail-closed guard even though
    # DB partial unique index should already
    # prevent this state.
    if len(
        current_battle_ids
    ) > 1:
        return None

    current_battle_id = (
        current_battle_ids[0]
        if current_battle_ids
        else None
    )

    return {
        "user_id":
            int(
                row["user_id"]
            ),

        "username":
            str(
                row["username"]
                or ""
            ),

        "display_name":
            str(
                row["display_name"]
                or ""
            ),

        # Compatibility / platform bootstrap only.
        "legacy_role":
            str(
                row["legacy_role"]
                or ""
            ),

        "workspace_id":
            workspace_id,

        "workspace_key":
            str(
                row["workspace_key"]
                or ""
            ),

        "workspace_name":
            str(
                row["workspace_name"]
                or ""
            ),

        "membership_id":
            int(
                row["membership_id"]
            ),

        "workspace_role":
            str(
                row["workspace_role"]
                or ""
            ),

        "permissions":
            permissions,

        "battle_ids":
            battle_ids,

        "current_battle_id":
            current_battle_id,
    }


def has_permission(
    context: dict[str, Any] | None,
    permission_key: str,
) -> bool:
    """
    Fail closed permission check.
    """

    if not context:
        return False

    key = str(
        permission_key
        or ""
    ).strip()

    if not key:
        return False

    permissions = context.get(
        "permissions"
    )

    if not isinstance(
        permissions,
        (
            set,
            frozenset,
        ),
    ):
        return False

    return key in permissions


def can_access_battle(
    context: dict[str, Any] | None,
    battle_id: int,
) -> bool:
    """
    Verify that a battle belongs to the resolved Workspace.
    """

    if not context:
        return False

    try:
        battle_id_value = int(
            battle_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return False

    if battle_id_value <= 0:
        return False

    battle_ids = context.get(
        "battle_ids"
    )

    if not isinstance(
        battle_ids,
        (
            tuple,
            list,
            set,
            frozenset,
        ),
    ):
        return False

    normalized_battle_ids = set()

    for value in battle_ids:
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            return False

        if normalized_value <= 0:
            return False

        normalized_battle_ids.add(
            normalized_value
        )

    return (
        battle_id_value
        in normalized_battle_ids
    )


def get_current_battle_id(
    context: dict[str, Any] | None,
) -> int | None:
    """
    Return Workspace-scoped current battle.
    """

    if not context:
        return None

    value = context.get(
        "current_battle_id"
    )

    if value is None:
        return None

    try:
        value = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    return (
        value
        if value > 0
        else None
    )
