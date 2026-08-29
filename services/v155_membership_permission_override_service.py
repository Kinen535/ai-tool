from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from services.v158_auth_store import record_action_log


PLATFORM_ONLY_PERMISSIONS = frozenset(
    {
        "account.manage",
        "security.manage",
    }
)

VALID_EFFECTS = frozenset(
    {
        "grant",
        "deny",
    }
)

VALID_AUDIT_METHODS = frozenset(
    {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "CLI",
        "SYSTEM",
    }
)


class MembershipPermissionOverrideError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        result_status: str = "blocked",
    ) -> None:
        super().__init__(message)

        self.code = str(
            code
            or "membership_permission_override_error"
        )[:64]

        self.message = str(
            message
            or "成员权限覆盖操作失败。"
        )[:500]

        self.result_status = (
            result_status
            if result_status
            in {
                "blocked",
                "failure",
            }
            else "blocked"
        )


def _fetchone_dict(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
) -> dict[str, Any] | None:
    cursor = conn.execute(
        sql,
        params,
    )

    row = cursor.fetchone()

    if row is None:
        return None

    columns = [
        item[0]
        for item in cursor.description
    ]

    return {
        column: row[index]
        for index, column
        in enumerate(columns)
    }


def _fetchall_dict(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    cursor = conn.execute(
        sql,
        params,
    )

    rows = cursor.fetchall()

    columns = [
        item[0]
        for item in cursor.description
    ]

    return [
        {
            column: row[index]
            for index, column
            in enumerate(columns)
        }
        for row in rows
    ]


def _audit_context(
    value: Mapping[str, Any] | None,
) -> dict[str, str]:
    value = value or {}

    request_method = str(
        value.get("request_method")
        or "POST"
    ).upper()[:16]

    if request_method not in VALID_AUDIT_METHODS:
        request_method = "POST"

    return {
        "request_method": request_method,
        "request_path": str(
            value.get("request_path")
            or ""
        )[:500],
        "ip_address": str(
            value.get("ip_address")
            or ""
        )[:64],
        "user_agent": str(
            value.get("user_agent")
            or ""
        )[:1000],
    }


def _get_user(
    conn: sqlite3.Connection,
    user_id: int,
) -> dict[str, Any] | None:
    return _fetchone_dict(
        conn,
        """
        SELECT
            id,
            username,
            display_name,
            role,
            status,
            session_version
        FROM v158_users
        WHERE id=?
        """,
        (
            int(user_id),
        ),
    )


def _actor_snapshot(
    actor: Mapping[str, Any] | None,
) -> tuple[
    int | None,
    str,
    str,
]:
    if not actor:
        return (
            None,
            "",
            "",
        )

    try:
        actor_id = int(
            actor.get("id")
        )

        if actor_id <= 0:
            actor_id = None

    except (
        TypeError,
        ValueError,
    ):
        actor_id = None

    role = str(
        actor.get("role")
        or ""
    )

    if role not in {
        "super_admin",
        "manager",
        "viewer",
    }:
        role = ""

    return (
        actor_id,
        str(
            actor.get("username")
            or ""
        )[:64],
        role,
    )


def _require_super_admin(
    conn: sqlite3.Connection,
    actor_user_id: int,
) -> dict[str, Any]:
    actor = _get_user(
        conn,
        int(actor_user_id),
    )

    if not actor:
        raise MembershipPermissionOverrideError(
            "actor_missing",
            "当前操作账号不存在。",
        )

    if str(
        actor.get("status")
        or ""
    ) != "active":
        raise MembershipPermissionOverrideError(
            "actor_disabled",
            "当前操作账号已经停用。",
        )

    if str(
        actor.get("role")
        or ""
    ) != "super_admin":
        raise MembershipPermissionOverrideError(
            "forbidden",
            "只有超级管理员可以管理成员权限覆盖。",
        )

    return actor


def _normalize_actor_user_id(
    value: Any,
) -> int:
    try:
        actor_user_id = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as error:
        raise MembershipPermissionOverrideError(
            "invalid_input",
            "操作账号编号无效。",
        ) from error

    if actor_user_id <= 0:
        raise MembershipPermissionOverrideError(
            "invalid_input",
            "操作账号编号无效。",
        )

    return actor_user_id


def _normalize_membership_id(
    value: Any,
) -> int:
    try:
        result = int(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise MembershipPermissionOverrideError(
            "invalid_membership",
            "成员关系编号无效。",
        ) from error

    if result <= 0:
        raise MembershipPermissionOverrideError(
            "invalid_membership",
            "成员关系编号无效。",
        )

    return result


def _normalize_permission_key(
    value: Any,
) -> str:
    key = str(
        value
        or ""
    ).strip()

    if not key:
        raise MembershipPermissionOverrideError(
            "permission_required",
            "权限标识不能为空。",
        )

    if len(key) > 120:
        raise MembershipPermissionOverrideError(
            "invalid_input",
            "权限标识长度无效。",
        )

    return key


def _normalize_effect(
    value: Any,
) -> str:
    effect = str(
        value
        or ""
    ).strip().lower()

    if effect not in VALID_EFFECTS:
        raise MembershipPermissionOverrideError(
            "invalid_effect",
            "权限覆盖类型必须为 grant 或 deny。",
        )

    return effect


def _require_target_membership(
    conn: sqlite3.Connection,
    membership_id: int,
) -> dict[str, Any]:
    row = _fetchone_dict(
        conn,
        """
        SELECT
            wm.id AS membership_id,
            wm.workspace_id,
            wm.user_id,
            wm.role_id,
            wm.status AS membership_status,
            wm.is_default,

            u.username,
            u.display_name,
            u.status AS user_status,

            w.workspace_key,
            w.workspace_name,
            w.status AS workspace_status,

            r.workspace_id AS role_workspace_id,
            r.role_key,
            r.role_name,
            r.status AS role_status

        FROM v155_workspace_members AS wm

        LEFT JOIN v158_users AS u
          ON u.id=wm.user_id

        LEFT JOIN v155_workspaces AS w
          ON w.id=wm.workspace_id

        LEFT JOIN v155_roles AS r
          ON r.id=wm.role_id

        WHERE wm.id=?
        """,
        (
            int(membership_id),
        ),
    )

    if not row:
        raise MembershipPermissionOverrideError(
            "membership_unavailable",
            "目标成员关系不存在。",
        )

    if (
        row.get("username") is None
        or row.get("workspace_key") is None
        or row.get("role_key") is None
    ):
        raise MembershipPermissionOverrideError(
            "membership_unavailable",
            "目标成员关系依赖的数据不存在。",
        )

    if str(
        row.get("user_status")
        or ""
    ) != "active":
        raise MembershipPermissionOverrideError(
            "membership_unavailable",
            "目标成员账号当前不可用。",
        )

    if str(
        row.get("membership_status")
        or ""
    ) != "active":
        raise MembershipPermissionOverrideError(
            "membership_unavailable",
            "目标成员关系当前不可用。",
        )

    if str(
        row.get("workspace_status")
        or ""
    ) != "active":
        raise MembershipPermissionOverrideError(
            "membership_unavailable",
            "目标工作空间当前不可用。",
        )

    if str(
        row.get("role_status")
        or ""
    ) != "active":
        raise MembershipPermissionOverrideError(
            "membership_unavailable",
            "目标成员角色当前不可用。",
        )

    if int(
        row.get("role_workspace_id")
        or 0
    ) != int(
        row.get("workspace_id")
        or 0
    ):
        raise MembershipPermissionOverrideError(
            "membership_unavailable",
            "目标角色不属于成员所在工作空间。",
        )

    return row


def _require_permission(
    conn: sqlite3.Connection,
    permission_key: str,
) -> dict[str, Any]:
    row = _fetchone_dict(
        conn,
        """
        SELECT
            id AS permission_id,
            permission_key,
            permission_name,
            module_key,
            description,
            is_system
        FROM v155_permissions
        WHERE permission_key=?
        """,
        (
            permission_key,
        ),
    )

    if not row:
        raise MembershipPermissionOverrideError(
            "permission_missing",
            "指定权限不存在。",
        )

    return row


def _grantable_permission_keys(
    conn: sqlite3.Connection,
    workspace_id: int,
) -> frozenset[str]:
    rows = _fetchall_dict(
        conn,
        """
        SELECT DISTINCT
            p.permission_key

        FROM v155_roles AS r

        JOIN v155_role_permissions AS rp
          ON rp.role_id=r.id

        JOIN v155_permissions AS p
          ON p.id=rp.permission_id

        WHERE r.workspace_id=?
          AND r.status='active'

        ORDER BY p.permission_key
        """,
        (
            int(workspace_id),
        ),
    )

    return frozenset(
        str(
            row.get("permission_key")
            or ""
        )
        for row in rows
        if row.get("permission_key")
        and str(
            row.get("permission_key")
        )
        not in PLATFORM_ONLY_PERMISSIONS
    )


def _role_permission_keys(
    conn: sqlite3.Connection,
    role_id: int,
) -> frozenset[str]:
    rows = _fetchall_dict(
        conn,
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
            int(role_id),
        ),
    )

    return frozenset(
        str(
            row.get("permission_key")
            or ""
        )
        for row in rows
        if row.get("permission_key")
        and str(
            row.get("permission_key")
        )
        not in PLATFORM_ONLY_PERMISSIONS
    )


def _stored_override(
    conn: sqlite3.Connection,
    *,
    membership_id: int,
    permission_id: int,
) -> dict[str, Any] | None:
    return _fetchone_dict(
        conn,
        """
        SELECT
            membership_id,
            permission_id,
            effect,
            created_at,
            updated_at
        FROM v155_membership_permission_overrides
        WHERE membership_id=?
          AND permission_id=?
        """,
        (
            int(membership_id),
            int(permission_id),
        ),
    )


def _safe_audit_state(
    *,
    membership: Mapping[str, Any] | None,
    permission_key: str,
    before_effect: str | None,
    after_effect: str | None,
) -> dict[str, Any]:
    membership = membership or {}

    return {
        "membership_id": (
            int(
                membership.get(
                    "membership_id"
                )
            )
            if membership.get(
                "membership_id"
            ) is not None
            else None
        ),
        "workspace_id": (
            int(
                membership.get(
                    "workspace_id"
                )
            )
            if membership.get(
                "workspace_id"
            ) is not None
            else None
        ),
        "user_id": (
            int(
                membership.get(
                    "user_id"
                )
            )
            if membership.get(
                "user_id"
            ) is not None
            else None
        ),
        "permission_key": str(
            permission_key
            or ""
        )[:120],
        "before_effect": (
            str(before_effect)
            if before_effect
            else None
        ),
        "after_effect": (
            str(after_effect)
            if after_effect
            else None
        ),
    }


def _record_override_action(
    conn: sqlite3.Connection,
    *,
    actor: Mapping[str, Any] | None,
    action_key: str,
    action_label: str,
    membership: Mapping[str, Any] | None,
    permission_key: str,
    result_status: str,
    before_effect: str | None,
    after_effect: str | None,
    reason: str,
    audit: Mapping[str, Any] | None,
) -> None:
    actor_id, actor_username, actor_role = (
        _actor_snapshot(
            actor
        )
    )

    context = _audit_context(
        audit
    )

    membership = membership or {}

    membership_id = (
        membership.get(
            "membership_id"
        )
    )

    username = str(
        membership.get(
            "username"
        )
        or ""
    )

    target_id = (
        f"{membership_id}:{permission_key}"
        if membership_id is not None
        else str(permission_key or "")
    )

    target_label = (
        f"{username} / {permission_key}"
        if username
        else str(permission_key or "")
    )

    before_data = _safe_audit_state(
        membership=membership,
        permission_key=permission_key,
        before_effect=before_effect,
        after_effect=before_effect,
    )

    after_data = _safe_audit_state(
        membership=membership,
        permission_key=permission_key,
        before_effect=before_effect,
        after_effect=after_effect,
    )

    record_action_log(
        conn,
        user_id=actor_id,
        username_snapshot=actor_username,
        role_snapshot=actor_role,
        action_key=str(
            action_key
        )[:100],
        action_label=str(
            action_label
        )[:200],
        target_type=(
            "workspace_membership_permission"
        ),
        target_id=target_id[:100],
        target_label=target_label[:300],
        result_status=result_status,
        before_data=before_data,
        after_data=after_data,
        reason=str(
            reason
            or ""
        )[:2000],
        request_method=(
            context["request_method"]
        ),
        request_path=(
            context["request_path"]
        ),
        ip_address=(
            context["ip_address"]
        ),
        user_agent=(
            context["user_agent"]
        ),
    )


def _begin_write(
    conn: sqlite3.Connection,
) -> None:
    if conn.in_transaction:
        raise MembershipPermissionOverrideError(
            "external_transaction",
            (
                "成员权限覆盖服务不接受"
                "外部未提交事务。"
            ),
        )

    conn.execute(
        "BEGIN IMMEDIATE"
    )


def _write_failure_audit(
    conn: sqlite3.Connection,
    *,
    actor: Mapping[str, Any] | None,
    action_key: str,
    action_label: str,
    membership: Mapping[str, Any] | None,
    permission_key: str,
    before_effect: str | None,
    reason: str,
    result_status: str,
    audit: Mapping[str, Any] | None,
) -> bool:
    if conn.in_transaction:
        conn.rollback()

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        _record_override_action(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            membership=membership,
            permission_key=permission_key,
            result_status=result_status,
            before_effect=before_effect,
            after_effect=before_effect,
            reason=reason,
            audit=audit,
        )

        conn.commit()

        return True

    except Exception:
        if conn.in_transaction:
            conn.rollback()

        return False


def _error_result(
    conn: sqlite3.Connection,
    *,
    error: Exception,
    actor: Mapping[str, Any] | None,
    action_key: str,
    action_label: str,
    membership: Mapping[str, Any] | None,
    permission_key: str,
    before_effect: str | None,
    audit: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(
        error,
        MembershipPermissionOverrideError,
    ):
        code = error.code
        message = error.message
        result_status = (
            error.result_status
        )
        audit_reason = (
            f"{code}: {message}"
        )

    elif isinstance(
        error,
        sqlite3.IntegrityError,
    ):
        code = "database_constraint"
        message = (
            "权限覆盖数据不符合数据库约束，"
            "操作已被拦截。"
        )
        result_status = "blocked"
        audit_reason = (
            f"{code}: {error}"
        )

    elif isinstance(
        error,
        ValueError,
    ):
        code = "invalid_input"
        message = str(
            error
        )[:500]
        result_status = "blocked"
        audit_reason = (
            f"{code}: {message}"
        )

    else:
        code = "internal_error"
        message = (
            "成员权限覆盖操作失败，"
            "数据库已经回滚。"
        )
        result_status = "failure"
        audit_reason = (
            f"{type(error).__name__}: {error}"
        )

    audit_written = (
        _write_failure_audit(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            membership=membership,
            permission_key=permission_key,
            before_effect=before_effect,
            reason=audit_reason,
            result_status=result_status,
            audit=audit,
        )
    )

    return {
        "ok": False,
        "code": code,
        "message": message,
        "result_status": result_status,
        "audit_written": audit_written,
    }


def _external_transaction_result() -> dict[str, Any]:
    return {
        "ok": False,
        "code": "external_transaction",
        "message": (
            "成员权限覆盖服务不接受"
            "外部未提交事务。"
        ),
        "result_status": "blocked",
        "audit_written": False,
    }


def get_membership_permission_admin_state(
    conn: sqlite3.Connection,
    *,
    target_membership_id: Any,
) -> dict[str, Any]:
    try:
        membership_id = (
            _normalize_membership_id(
                target_membership_id
            )
        )

        membership = (
            _require_target_membership(
                conn,
                membership_id,
            )
        )

        role_permissions = (
            _role_permission_keys(
                conn,
                int(
                    membership[
                        "role_id"
                    ]
                ),
            )
        )

        grantable_permissions = (
            _grantable_permission_keys(
                conn,
                int(
                    membership[
                        "workspace_id"
                    ]
                ),
            )
        )

        catalog = _fetchall_dict(
            conn,
            """
            SELECT
                id AS permission_id,
                permission_key,
                permission_name,
                module_key,
                description,
                is_system
            FROM v155_permissions
            ORDER BY
                module_key,
                permission_key
            """,
        )

        override_rows = (
            _fetchall_dict(
                conn,
                """
                SELECT
                    o.permission_id,
                    p.permission_key,
                    o.effect,
                    o.created_at,
                    o.updated_at

                FROM
                    v155_membership_permission_overrides
                    AS o

                JOIN v155_permissions AS p
                  ON p.id=o.permission_id

                WHERE o.membership_id=?

                ORDER BY p.permission_key
                """,
                (
                    membership_id,
                ),
            )
        )

        overrides_by_key: dict[
            str,
            str,
        ] = {}

        stored_overrides = []

        for row in override_rows:
            permission_key = str(
                row.get(
                    "permission_key"
                )
                or ""
            ).strip()

            effect = str(
                row.get(
                    "effect"
                )
                or ""
            ).strip().lower()

            if (
                not permission_key
                or effect
                not in VALID_EFFECTS
            ):
                raise MembershipPermissionOverrideError(
                    "database_constraint",
                    (
                        "发现不符合约束的"
                        "权限覆盖记录。"
                    ),
                    result_status="failure",
                )

            overrides_by_key[
                permission_key
            ] = effect

            is_grantable = (
                permission_key
                in grantable_permissions
            )

            is_platform_only = (
                permission_key
                in PLATFORM_ONLY_PERMISSIONS
            )

            stored_overrides.append(
                {
                    "permission_id": int(
                        row[
                            "permission_id"
                        ]
                    ),
                    "permission_key": (
                        permission_key
                    ),
                    "effect": effect,
                    "grantable": (
                        is_grantable
                    ),
                    "platform_only": (
                        is_platform_only
                    ),
                    "stale": (
                        is_platform_only
                        or not is_grantable
                    ),
                    "created_at": row.get(
                        "created_at"
                    ),
                    "updated_at": row.get(
                        "updated_at"
                    ),
                }
            )

        membership_grants = {
            key
            for key, effect
            in overrides_by_key.items()
            if (
                effect == "grant"
                and key
                in grantable_permissions
                and key
                not in PLATFORM_ONLY_PERMISSIONS
            )
        }

        membership_denies = {
            key
            for key, effect
            in overrides_by_key.items()
            if effect == "deny"
        }

        effective_permissions = (
            (
                role_permissions
                | membership_grants
            )
            - membership_denies
        )

        effective_permissions = frozenset(
            permission
            for permission
            in effective_permissions
            if permission
            not in PLATFORM_ONLY_PERMISSIONS
        )

        permission_rows = []

        for row in catalog:
            permission_key = str(
                row.get(
                    "permission_key"
                )
                or ""
            )

            effect = overrides_by_key.get(
                permission_key
            )

            permission_rows.append(
                {
                    "permission_id": int(
                        row[
                            "permission_id"
                        ]
                    ),
                    "permission_key": (
                        permission_key
                    ),
                    "permission_name": str(
                        row.get(
                            "permission_name"
                        )
                        or ""
                    ),
                    "module_key": str(
                        row.get(
                            "module_key"
                        )
                        or ""
                    ),
                    "description": str(
                        row.get(
                            "description"
                        )
                        or ""
                    ),
                    "is_system": int(
                        row.get(
                            "is_system"
                        )
                        or 0
                    ),
                    "role_baseline": (
                        permission_key
                        in role_permissions
                    ),
                    "grantable": (
                        permission_key
                        in grantable_permissions
                    ),
                    "platform_only": (
                        permission_key
                        in PLATFORM_ONLY_PERMISSIONS
                    ),
                    "override_effect": (
                        effect
                    ),
                    "effective": (
                        permission_key
                        in effective_permissions
                    ),
                }
            )

        return {
            "ok": True,
            "membership": dict(
                membership
            ),
            "role_baseline_permissions": sorted(
                role_permissions
            ),
            "grantable_permissions": sorted(
                grantable_permissions
            ),
            "stored_overrides": (
                stored_overrides
            ),
            "effective_permissions": sorted(
                effective_permissions
            ),
            "permissions": permission_rows,
        }

    except Exception as error:
        if isinstance(
            error,
            MembershipPermissionOverrideError,
        ):
            code = error.code
            message = error.message
            result_status = (
                error.result_status
            )
        else:
            code = "internal_error"
            message = (
                "读取成员权限覆盖状态失败。"
            )
            result_status = "failure"

        return {
            "ok": False,
            "code": code,
            "message": message,
            "result_status": result_status,
            "audit_written": False,
        }


def set_membership_permission_override(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    target_membership_id: Any,
    permission_key: Any,
    effect: Any,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if conn.in_transaction:
        return _external_transaction_result()

    actor: dict[str, Any] | None = None
    actor_user_id_value: int | None = None

    membership: dict[str, Any] | None = None
    normalized_key = str(
        permission_key
        or ""
    ).strip()

    before_effect: str | None = None

    normalized_effect = str(
        effect
        or ""
    ).strip().lower()

    action_key = (
        "membership_permission_grant"
        if normalized_effect == "grant"
        else (
            "membership_permission_deny"
            if normalized_effect == "deny"
            else "membership_permission_set"
        )
    )

    action_label = (
        "设置成员权限授予"
        if normalized_effect == "grant"
        else (
            "设置成员权限拒绝"
            if normalized_effect == "deny"
            else "设置成员权限覆盖"
        )
    )

    try:
        actor_user_id_value = (
            _normalize_actor_user_id(
                actor_user_id
            )
        )

        actor = _require_super_admin(
            conn,
            actor_user_id_value,
        )

        membership_id = (
            _normalize_membership_id(
                target_membership_id
            )
        )

        normalized_key = (
            _normalize_permission_key(
                permission_key
            )
        )

        normalized_effect = (
            _normalize_effect(
                effect
            )
        )

        membership = (
            _require_target_membership(
                conn,
                membership_id,
            )
        )

        permission = (
            _require_permission(
                conn,
                normalized_key,
            )
        )

        if (
            normalized_key
            in PLATFORM_ONLY_PERMISSIONS
        ):
            raise MembershipPermissionOverrideError(
                "platform_permission_forbidden",
                "平台级权限不能通过工作空间成员覆盖授予或拒绝。",
            )

        grantable = (
            _grantable_permission_keys(
                conn,
                int(
                    membership[
                        "workspace_id"
                    ]
                ),
            )
        )

        if normalized_key not in grantable:
            raise MembershipPermissionOverrideError(
                "permission_not_grantable",
                "该权限不属于目标工作空间的可授权权限集合。",
            )

        existing = _stored_override(
            conn,
            membership_id=membership_id,
            permission_id=int(
                permission[
                    "permission_id"
                ]
            ),
        )

        before_effect = (
            str(
                existing.get(
                    "effect"
                )
            )
            if existing
            else None
        )

        _begin_write(
            conn
        )

        actor = _require_super_admin(
            conn,
            actor_user_id_value,
        )

        membership = (
            _require_target_membership(
                conn,
                membership_id,
            )
        )

        permission = (
            _require_permission(
                conn,
                normalized_key,
            )
        )

        if (
            normalized_key
            in PLATFORM_ONLY_PERMISSIONS
        ):
            raise MembershipPermissionOverrideError(
                "platform_permission_forbidden",
                "平台级权限不能通过工作空间成员覆盖授予或拒绝。",
            )

        grantable = (
            _grantable_permission_keys(
                conn,
                int(
                    membership[
                        "workspace_id"
                    ]
                ),
            )
        )

        if normalized_key not in grantable:
            raise MembershipPermissionOverrideError(
                "permission_not_grantable",
                "该权限不属于目标工作空间的可授权权限集合。",
            )

        existing = _stored_override(
            conn,
            membership_id=membership_id,
            permission_id=int(
                permission[
                    "permission_id"
                ]
            ),
        )

        before_effect = (
            str(
                existing.get(
                    "effect"
                )
            )
            if existing
            else None
        )

        changed = (
            before_effect
            != normalized_effect
        )

        conn.execute(
            """
            INSERT INTO
                v155_membership_permission_overrides (
                    membership_id,
                    permission_id,
                    effect
                )
            VALUES (?, ?, ?)

            ON CONFLICT(
                membership_id,
                permission_id
            )
            DO UPDATE SET
                effect=excluded.effect,
                updated_at=
                    CASE
                        WHEN
                            v155_membership_permission_overrides.effect
                            <> excluded.effect
                        THEN datetime(
                            'now',
                            'localtime'
                        )
                        ELSE
                            v155_membership_permission_overrides.updated_at
                    END
            """,
            (
                membership_id,
                int(
                    permission[
                        "permission_id"
                    ]
                ),
                normalized_effect,
            ),
        )

        stored = _stored_override(
            conn,
            membership_id=membership_id,
            permission_id=int(
                permission[
                    "permission_id"
                ]
            ),
        )

        if (
            not stored
            or str(
                stored.get(
                    "effect"
                )
                or ""
            )
            != normalized_effect
        ):
            raise RuntimeError(
                "权限覆盖写入后状态校验失败。"
            )

        _record_override_action(
            conn,
            actor=actor,
            action_key=(
                "membership_permission_grant"
                if normalized_effect
                == "grant"
                else "membership_permission_deny"
            ),
            action_label=(
                "设置成员权限授予"
                if normalized_effect
                == "grant"
                else "设置成员权限拒绝"
            ),
            membership=membership,
            permission_key=normalized_key,
            result_status="success",
            before_effect=before_effect,
            after_effect=normalized_effect,
            reason=(
                "成员权限覆盖已变更。"
                if changed
                else "成员权限覆盖状态未变化。"
            ),
            audit=audit,
        )

        conn.commit()

        return {
            "ok": True,
            "code": (
                "override_set"
                if changed
                else "override_unchanged"
            ),
            "message": (
                "成员权限覆盖已更新。"
                if changed
                else "成员权限覆盖已经是目标状态。"
            ),
            "result_status": "success",
            "changed": changed,
            "membership_id": membership_id,
            "workspace_id": int(
                membership[
                    "workspace_id"
                ]
            ),
            "user_id": int(
                membership[
                    "user_id"
                ]
            ),
            "permission_key": normalized_key,
            "before_effect": before_effect,
            "after_effect": normalized_effect,
            "audit_written": True,
        }

    except Exception as error:
        return _error_result(
            conn,
            error=error,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            membership=membership,
            permission_key=normalized_key,
            before_effect=before_effect,
            audit=audit,
        )


def clear_membership_permission_override(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    target_membership_id: Any,
    permission_key: Any,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if conn.in_transaction:
        return _external_transaction_result()

    actor: dict[str, Any] | None = None
    actor_user_id_value: int | None = None

    membership: dict[str, Any] | None = None

    normalized_key = str(
        permission_key
        or ""
    ).strip()

    before_effect: str | None = None

    try:
        actor_user_id_value = (
            _normalize_actor_user_id(
                actor_user_id
            )
        )

        actor = _require_super_admin(
            conn,
            actor_user_id_value,
        )

        membership_id = (
            _normalize_membership_id(
                target_membership_id
            )
        )

        normalized_key = (
            _normalize_permission_key(
                permission_key
            )
        )

        membership = (
            _require_target_membership(
                conn,
                membership_id,
            )
        )

        permission = (
            _require_permission(
                conn,
                normalized_key,
            )
        )

        existing = _stored_override(
            conn,
            membership_id=membership_id,
            permission_id=int(
                permission[
                    "permission_id"
                ]
            ),
        )

        before_effect = (
            str(
                existing.get(
                    "effect"
                )
            )
            if existing
            else None
        )

        _begin_write(
            conn
        )

        actor = _require_super_admin(
            conn,
            actor_user_id_value,
        )

        membership = (
            _require_target_membership(
                conn,
                membership_id,
            )
        )

        permission = (
            _require_permission(
                conn,
                normalized_key,
            )
        )

        existing = _stored_override(
            conn,
            membership_id=membership_id,
            permission_id=int(
                permission[
                    "permission_id"
                ]
            ),
        )

        before_effect = (
            str(
                existing.get(
                    "effect"
                )
            )
            if existing
            else None
        )

        changed = (
            existing is not None
        )

        if changed:
            cursor = conn.execute(
                """
                DELETE FROM
                    v155_membership_permission_overrides
                WHERE membership_id=?
                  AND permission_id=?
                """,
                (
                    membership_id,
                    int(
                        permission[
                            "permission_id"
                        ]
                    ),
                ),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "权限覆盖清除行数异常。"
                )

        remaining = _stored_override(
            conn,
            membership_id=membership_id,
            permission_id=int(
                permission[
                    "permission_id"
                ]
            ),
        )

        if remaining is not None:
            raise RuntimeError(
                "权限覆盖清除后状态校验失败。"
            )

        _record_override_action(
            conn,
            actor=actor,
            action_key=(
                "membership_permission_clear"
            ),
            action_label=(
                "清除成员权限覆盖"
            ),
            membership=membership,
            permission_key=normalized_key,
            result_status="success",
            before_effect=before_effect,
            after_effect=None,
            reason=(
                "成员权限覆盖已清除。"
                if changed
                else "成员权限覆盖原本即为空。"
            ),
            audit=audit,
        )

        conn.commit()

        return {
            "ok": True,
            "code": (
                "override_cleared"
                if changed
                else "override_already_clear"
            ),
            "message": (
                "成员权限覆盖已清除。"
                if changed
                else "该权限当前没有覆盖记录。"
            ),
            "result_status": "success",
            "changed": changed,
            "membership_id": membership_id,
            "workspace_id": int(
                membership[
                    "workspace_id"
                ]
            ),
            "user_id": int(
                membership[
                    "user_id"
                ]
            ),
            "permission_key": normalized_key,
            "before_effect": before_effect,
            "after_effect": None,
            "audit_written": True,
        }

    except Exception as error:
        return _error_result(
            conn,
            error=error,
            actor=actor,
            action_key=(
                "membership_permission_clear"
            ),
            action_label=(
                "清除成员权限覆盖"
            ),
            membership=membership,
            permission_key=normalized_key,
            before_effect=before_effect,
            audit=audit,
        )
