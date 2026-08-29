from __future__ import annotations

import sqlite3
from typing import Any, Dict, List


def build_access_center_report(
    conn: sqlite3.Connection,
) -> Dict[str, Any]:

    report = {
        "stats": {},
        "users": [],
        "roles": [],
        "role_permissions": [],
        "workspaces": [],
    }


    report["stats"]["user_count"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM v158_users
        """
    ).fetchone()[0]


    report["stats"]["role_count"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_roles
        """
    ).fetchone()[0]


    report["stats"]["permission_count"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_permissions
        """
    ).fetchone()[0]


    report["stats"]["workspace_count"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_workspaces
        """
    ).fetchone()[0]


    report["stats"]["battle_count"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_workspace_battles
        """
    ).fetchone()[0]


    users = conn.execute(
        """
        SELECT
            u.id AS user_id,
            u.username,
            u.display_name,
            u.role AS account_role,
            u.status,

            wm.id AS membership_id,
            wm.status AS membership_status,
            wm.is_default,

            w.id AS workspace_id,
            w.workspace_key,
            w.workspace_name,
            w.status AS workspace_status,

            r.id AS workspace_role_id,
            r.role_key AS workspace_role_key,
            r.role_name AS workspace_role,
            r.status AS workspace_role_status,
            r.workspace_id AS role_workspace_id

        FROM v158_users u

        LEFT JOIN v155_workspace_members wm
        ON wm.user_id=u.id

        LEFT JOIN v155_workspaces w
        ON w.id=wm.workspace_id

        LEFT JOIN v155_roles r
        ON r.id=wm.role_id
        AND r.workspace_id=wm.workspace_id

        ORDER BY
            u.id,
            wm.id
        """
    )


    for row in users:
        report["users"].append(dict(row))


    roles = conn.execute(
        """
        SELECT
            r.role_key,
            r.role_name,
            COUNT(rp.permission_id) AS permission_count

        FROM v155_roles r

        LEFT JOIN v155_role_permissions rp
        ON rp.role_id=r.id

        GROUP BY r.id

        ORDER BY r.id
        """
    )


    for row in roles:
        report["roles"].append(dict(row))


    role_permissions = conn.execute(
        """
        SELECT
            r.role_key,
            r.role_name,
            p.permission_key,
            p.permission_name,
            p.module_key

        FROM v155_roles r

        LEFT JOIN v155_role_permissions rp
        ON rp.role_id = r.id

        LEFT JOIN v155_permissions p
        ON p.id = rp.permission_id

        ORDER BY
            r.id,
            p.module_key,
            p.id
        """
    )


    grouped = {}

    for row in role_permissions:

        key = (
            row["role_key"],
            row["role_name"],
        )

        if key not in grouped:
            grouped[key] = {
                "role_key": row["role_key"],
                "role_name": row["role_name"],
                "permissions": [],
            }

        if row["permission_key"]:

            grouped[key]["permissions"].append(
                {
                    "permission_key": row["permission_key"],
                    "permission_name": row["permission_name"],
                    "module_key": row["module_key"],
                }
            )


    report["role_permissions"] = list(
        grouped.values()
    )


    workspaces = conn.execute(
        """
        SELECT
            w.workspace_key,
            w.workspace_name,

            COUNT(wb.battle_id) AS battle_count

        FROM v155_workspaces w

        LEFT JOIN v155_workspace_battles wb

        ON wb.workspace_id=w.id

        GROUP BY w.id
        """
    )


    for row in workspaces:
        report["workspaces"].append(dict(row))


    return report
