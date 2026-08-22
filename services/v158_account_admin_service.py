from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from services.v155_workspace_provisioning import (
    ensure_default_workspace_membership,
)

from services.v158_auth_store import (
    create_user,
    get_user_by_id,
    get_user_by_username,
    normalize_username,
    record_action_log,
    record_login_event,
    validate_role,
    validate_user_status,
    validate_username,
)


ROLE_LABELS = {
    "super_admin": "超级管理员",
    "manager": "管理员",
    "viewer": "只读用户",
}

STATUS_LABELS = {
    "active": "启用",
    "disabled": "停用",
}

VALID_AUDIT_METHODS = {
    "",
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "CLI",
    "SYSTEM",
}

SAFE_USER_FIELDS = (
    "id",
    "username",
    "display_name",
    "role",
    "status",
    "failed_login_count",
    "locked_until",
    "last_failed_login_at",
    "last_login_at",
    "last_login_ip",
    "password_changed_at",
    "must_change_password",
    "session_version",
    "created_at",
    "updated_at",
)


class AccountAdminError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        result_status: str = "blocked",
    ) -> None:
        super().__init__(message)

        self.code = str(code or "account_admin_error")[:64]
        self.message = str(message or "账号管理操作失败。")[:500]
        self.result_status = (
            result_status
            if result_status in {
                "blocked",
                "failure",
            }
            else "blocked"
        )


def _safe_user(
    user: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not user:
        return None

    result = {
        field: user.get(field)
        for field in SAFE_USER_FIELDS
    }

    role = str(
        result.get("role")
        or ""
    )

    status = str(
        result.get("status")
        or ""
    )

    result["role_label"] = (
        ROLE_LABELS.get(
            role,
            role,
        )
    )

    result["status_label"] = (
        STATUS_LABELS.get(
            status,
            status,
        )
    )

    return result


def _normalize_display_name(
    value: Any,
    *,
    fallback: str,
) -> str:
    display_name = str(
        value or ""
    ).strip()

    if not display_name:
        display_name = str(
            fallback or ""
        ).strip()

    if not display_name:
        raise AccountAdminError(
            "display_name_required",
            "显示名称不能为空。",
        )

    if len(display_name) > 100:
        raise AccountAdminError(
            "display_name_too_long",
            "显示名称不能超过100个字符。",
        )

    return display_name


def validate_account_password(
    password: Any,
    *,
    username: str = "",
) -> str:
    password = str(
        password or ""
    )

    username = normalize_username(
        username
    )

    if password != password.strip():
        raise AccountAdminError(
            "password_whitespace",
            "密码首尾不能包含空格。",
        )

    if len(password) < 12:
        raise AccountAdminError(
            "password_too_short",
            "密码至少需要12个字符。",
        )

    if len(password) > 128:
        raise AccountAdminError(
            "password_too_long",
            "密码不能超过128个字符。",
        )

    categories = (
        any(
            character.islower()
            for character in password
        ),
        any(
            character.isupper()
            for character in password
        ),
        any(
            character.isdigit()
            for character in password
        ),
        any(
            not character.isalnum()
            for character in password
        ),
    )

    if sum(categories) < 3:
        raise AccountAdminError(
            "password_complexity",
            (
                "密码必须至少包含以下四类中的三类："
                "大写字母、小写字母、数字、特殊字符。"
            ),
        )

    if (
        username
        and username.casefold()
        in password.casefold()
    ):
        raise AccountAdminError(
            "password_contains_username",
            "密码不能包含完整用户名。",
        )

    return password


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
    actor = get_user_by_id(
        conn,
        int(actor_user_id),
    )

    if not actor:
        raise AccountAdminError(
            "actor_missing",
            "当前操作账号不存在。",
        )

    if str(
        actor.get("status")
        or ""
    ) != "active":
        raise AccountAdminError(
            "actor_disabled",
            "当前操作账号已经停用。",
        )

    if str(
        actor.get("role")
        or ""
    ) != "super_admin":
        raise AccountAdminError(
            "forbidden",
            "只有超级管理员可以管理系统账号。",
        )

    return actor


def _require_target(
    conn: sqlite3.Connection,
    target_user_id: int,
) -> dict[str, Any]:
    target = get_user_by_id(
        conn,
        int(target_user_id),
    )

    if not target:
        raise AccountAdminError(
            "target_missing",
            "目标账号不存在。",
        )

    return target


def _active_super_admin_count(
    conn: sqlite3.Connection,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM v158_users
        WHERE
            role='super_admin'
            AND status='active'
        """
    ).fetchone()

    return int(
        row[0] or 0
    ) if row else 0


def _begin_write(
    conn: sqlite3.Connection,
) -> None:
    if conn.in_transaction:
        raise RuntimeError(
            "账号管理服务不接受外部未提交事务。"
        )

    conn.execute(
        "BEGIN IMMEDIATE"
    )


def _record_account_action(
    conn: sqlite3.Connection,
    *,
    actor: Mapping[str, Any] | None,
    action_key: str,
    action_label: str,
    target_id: str,
    target_label: str,
    result_status: str,
    before_data: Mapping[str, Any] | None = None,
    after_data: Mapping[str, Any] | None = None,
    reason: str = "",
    audit: Mapping[str, Any] | None = None,
) -> None:
    actor_id, actor_username, actor_role = (
        _actor_snapshot(
            actor
        )
    )

    context = _audit_context(
        audit
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
        target_type="user",
        target_id=str(
            target_id
        )[:100],
        target_label=str(
            target_label
        )[:300],
        result_status=result_status,
        before_data=dict(
            before_data or {}
        ),
        after_data=dict(
            after_data or {}
        ),
        reason=str(
            reason or ""
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


def _write_failure_audit(
    conn: sqlite3.Connection,
    *,
    actor: Mapping[str, Any] | None,
    action_key: str,
    action_label: str,
    target_id: str,
    target_label: str,
    result_status: str,
    before_data: Mapping[str, Any] | None,
    reason: str,
    audit: Mapping[str, Any] | None,
) -> bool:
    if conn.in_transaction:
        conn.rollback()

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        _record_account_action(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=target_id,
            target_label=target_label,
            result_status=result_status,
            before_data=before_data,
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
    target_id: str,
    target_label: str,
    before_data: Mapping[str, Any] | None,
    audit: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(
        error,
        AccountAdminError,
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
            "账号数据不符合数据库约束，操作已被拦截。"
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
            "账号管理操作失败，数据库已经回滚。"
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
            target_id=target_id,
            target_label=target_label,
            result_status=result_status,
            before_data=before_data,
            reason=audit_reason,
            audit=audit,
        )
    )

    return {
        "ok": False,
        "code": code,
        "message": message,
        "result_status": (
            result_status
        ),
        "audit_written": (
            audit_written
        ),
    }


def list_accounts(
    conn: sqlite3.Connection,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    limit = max(
        1,
        min(
            int(limit),
            500,
        ),
    )

    rows = conn.execute(
        """
        SELECT
            id,
            username,
            display_name,
            role,
            status,
            failed_login_count,
            locked_until,
            last_failed_login_at,
            last_login_at,
            last_login_ip,
            password_changed_at,
            must_change_password,
            session_version,
            created_at,
            updated_at,
            CASE
                WHEN
                    locked_until IS NOT NULL
                    AND locked_until >
                        datetime(
                            'now',
                            'localtime'
                        )
                THEN 1
                ELSE 0
            END AS is_locked
        FROM v158_users
        ORDER BY
            CASE role
                WHEN 'super_admin' THEN 1
                WHEN 'manager' THEN 2
                ELSE 3
            END,
            CASE status
                WHEN 'active' THEN 1
                ELSE 2
            END,
            lower(username),
            id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    result = []

    for row in rows:
        user = _safe_user(
            dict(row)
        )

        if user is None:
            continue

        user["is_locked"] = int(
            row["is_locked"] or 0
        )

        result.append(
            user
        )

    return result


def build_account_admin_report(
    conn: sqlite3.Connection,
    *,
    recent_limit: int = 30,
) -> dict[str, Any]:
    recent_limit = max(
        1,
        min(
            int(recent_limit),
            200,
        ),
    )

    stats_row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_users,

            SUM(
                CASE
                    WHEN status='active'
                    THEN 1
                    ELSE 0
                END
            ) AS active_users,

            SUM(
                CASE
                    WHEN status='disabled'
                    THEN 1
                    ELSE 0
                END
            ) AS disabled_users,

            SUM(
                CASE
                    WHEN
                        role='super_admin'
                        AND status='active'
                    THEN 1
                    ELSE 0
                END
            ) AS active_super_admins,

            SUM(
                CASE
                    WHEN
                        locked_until IS NOT NULL
                        AND locked_until >
                            datetime(
                                'now',
                                'localtime'
                            )
                    THEN 1
                    ELSE 0
                END
            ) AS locked_users
        FROM v158_users
        """
    ).fetchone()

    stats = {
        key: int(
            stats_row[key] or 0
        )
        for key in (
            "total_users",
            "active_users",
            "disabled_users",
            "active_super_admins",
            "locked_users",
        )
    }

    recent_rows = conn.execute(
        """
        SELECT
            id,
            user_id,
            username_snapshot,
            role_snapshot,
            action_key,
            action_label,
            target_id,
            target_label,
            result_status,
            reason,
            request_method,
            request_path,
            ip_address,
            created_at
        FROM v158_action_logs
        WHERE
            target_type='user'
            AND (
                action_key LIKE 'account_%'
                OR action_key='bootstrap_super_admin'
            )
        ORDER BY id DESC
        LIMIT ?
        """,
        (recent_limit,),
    ).fetchall()

    return {
        "stats": stats,
        "users": list_accounts(
            conn
        ),
        "recent_actions": [
            dict(row)
            for row in recent_rows
        ],
        "role_labels": dict(
            ROLE_LABELS
        ),
        "status_labels": dict(
            STATUS_LABELS
        ),
    }


def create_account(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    username: Any,
    display_name: Any,
    role: Any,
    status: Any,
    password: Any,
    must_change_password: bool = True,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action_key = "account_create"
    action_label = "创建系统账号"

    username = normalize_username(
        username
    )

    target_id = username
    target_label = username
    actor = get_user_by_id(
        conn,
        int(actor_user_id),
    )

    try:
        # Fail closed before input validation or write-lock acquisition.
        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        validate_username(
            username
        )

        role = str(
            role or ""
        ).strip()

        status = str(
            status or ""
        ).strip()

        validate_role(
            role
        )

        validate_user_status(
            status
        )

        display_name = (
            _normalize_display_name(
                display_name,
                fallback=username,
            )
        )

        password = (
            validate_account_password(
                password,
                username=username,
            )
        )

        password_hash = (
            generate_password_hash(
                password,
                method="scrypt",
            )
        )

        if not check_password_hash(
            password_hash,
            password,
        ):
            raise RuntimeError(
                "密码哈希自检失败。"
            )

        _begin_write(
            conn
        )

        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        if get_user_by_username(
            conn,
            username,
        ):
            raise AccountAdminError(
                "username_exists",
                "用户名已经存在。",
            )

        user_id = create_user(
            conn,
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            status=status,
            must_change_password=(
                bool(
                    must_change_password
                )
            ),
        )

        ensure_default_workspace_membership(
            conn,
            user_id=user_id,
            account_role=role,
        )

        created = _require_target(
            conn,
            user_id,
        )

        safe_created = _safe_user(
            created
        )

        _record_account_action(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=str(user_id),
            target_label=username,
            result_status="success",
            after_data=safe_created,
            reason=(
                "超级管理员创建系统账号。"
            ),
            audit=audit,
        )

        conn.commit()

        return {
            "ok": True,
            "code": "created",
            "message": "账号创建成功。",
            "result_status": "success",
            "user": safe_created,
            "audit_written": True,
        }

    except Exception as error:
        return _error_result(
            conn,
            error=error,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=target_id,
            target_label=target_label,
            before_data=None,
            audit=audit,
        )


def update_account_access(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    target_user_id: int,
    display_name: Any,
    role: Any,
    status: Any,
    invalidate_sessions: bool = False,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action_key = (
        "account_update_access"
    )

    action_label = (
        "修改账号资料与权限"
    )

    actor = get_user_by_id(
        conn,
        int(actor_user_id),
    )

    target = get_user_by_id(
        conn,
        int(target_user_id),
    )

    safe_before = _safe_user(
        target
    )

    target_label = str(
        (
            target or {}
        ).get(
            "username"
        )
        or target_user_id
    )

    try:
        # Fail closed before input validation or write-lock acquisition.
        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        role = str(
            role or ""
        ).strip()

        status = str(
            status or ""
        ).strip()

        validate_role(
            role
        )

        validate_user_status(
            status
        )

        display_name = (
            _normalize_display_name(
                display_name,
                fallback=target_label,
            )
        )

        _begin_write(
            conn
        )

        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        target = _require_target(
            conn,
            int(target_user_id),
        )

        safe_before = _safe_user(
            target
        )

        target_label = str(
            target.get("username")
            or target_user_id
        )

        removes_active_super_admin = (
            str(
                target.get("role")
                or ""
            )
            == "super_admin"
            and str(
                target.get("status")
                or ""
            )
            == "active"
            and not (
                role == "super_admin"
                and status == "active"
            )
        )

        if (
            removes_active_super_admin
            and _active_super_admin_count(
                conn
            )
            <= 1
        ):
            raise AccountAdminError(
                "last_active_super_admin",
                (
                    "系统必须保留至少一个启用状态的"
                    "超级管理员，当前操作已被拦截。"
                ),
            )

        role_changed = (
            str(
                target.get("role")
                or ""
            )
            != role
        )

        status_changed = (
            str(
                target.get("status")
                or ""
            )
            != status
        )

        should_invalidate = (
            bool(
                invalidate_sessions
            )
            or role_changed
            or status_changed
        )

        if status_changed:
            failed_login_count = 0
            locked_until = None
            last_failed_login_at = None
        else:
            failed_login_count = int(
                target.get(
                    "failed_login_count"
                )
                or 0
            )

            locked_until = (
                target.get(
                    "locked_until"
                )
            )

            last_failed_login_at = (
                target.get(
                    "last_failed_login_at"
                )
            )

        cursor = conn.execute(
            """
            UPDATE v158_users
            SET
                display_name=?,
                role=?,
                status=?,
                failed_login_count=?,
                locked_until=?,
                last_failed_login_at=?,
                session_version=
                    session_version + ?,
                updated_at=datetime(
                    'now',
                    'localtime'
                )
            WHERE id=?
            """,
            (
                display_name,
                role,
                status,
                failed_login_count,
                locked_until,
                last_failed_login_at,
                (
                    1
                    if should_invalidate
                    else 0
                ),
                int(target_user_id),
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "账号更新行数异常。"
            )

        updated = _require_target(
            conn,
            int(target_user_id),
        )

        safe_updated = _safe_user(
            updated
        )

        _record_account_action(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=str(
                target_user_id
            ),
            target_label=target_label,
            result_status="success",
            before_data=safe_before,
            after_data=safe_updated,
            reason=(
                "权限或状态变化将强制旧会话失效。"
                if should_invalidate
                else "仅更新账号显示资料。"
            ),
            audit=audit,
        )

        conn.commit()

        return {
            "ok": True,
            "code": "updated",
            "message": (
                "账号资料与权限已更新。"
            ),
            "result_status": "success",
            "user": safe_updated,
            "sessions_invalidated": (
                should_invalidate
            ),
            "audit_written": True,
        }

    except Exception as error:
        return _error_result(
            conn,
            error=error,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=str(
                target_user_id
            ),
            target_label=target_label,
            before_data=safe_before,
            audit=audit,
        )


def unlock_account(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    target_user_id: int,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action_key = "account_unlock"
    action_label = "解除账号登录锁定"

    actor = get_user_by_id(
        conn,
        int(actor_user_id),
    )

    target = get_user_by_id(
        conn,
        int(target_user_id),
    )

    safe_before = _safe_user(
        target
    )

    target_label = str(
        (
            target or {}
        ).get(
            "username"
        )
        or target_user_id
    )

    try:
        # Fail closed before input validation or write-lock acquisition.
        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        _begin_write(
            conn
        )

        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        target = _require_target(
            conn,
            int(target_user_id),
        )

        safe_before = _safe_user(
            target
        )

        target_label = str(
            target.get("username")
            or target_user_id
        )

        cursor = conn.execute(
            """
            UPDATE v158_users
            SET
                failed_login_count=0,
                locked_until=NULL,
                last_failed_login_at=NULL,
                updated_at=datetime(
                    'now',
                    'localtime'
                )
            WHERE id=?
            """,
            (
                int(target_user_id),
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "账号解锁行数异常。"
            )

        updated = _require_target(
            conn,
            int(target_user_id),
        )

        safe_updated = _safe_user(
            updated
        )

        context = _audit_context(
            audit
        )

        record_login_event(
            conn,
            user_id=int(
                target_user_id
            ),
            username_snapshot=(
                target_label
            ),
            event_type=(
                "account_unlocked"
            ),
            result_status="success",
            reason_code="admin_unlock",
            ip_address=(
                context["ip_address"]
            ),
            user_agent=(
                context["user_agent"]
            ),
            request_path=(
                context["request_path"]
            ),
            session_version=int(
                updated.get(
                    "session_version"
                )
                or 1
            ),
        )

        _record_account_action(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=str(
                target_user_id
            ),
            target_label=target_label,
            result_status="success",
            before_data=safe_before,
            after_data=safe_updated,
            reason=(
                "超级管理员解除账号临时锁定。"
            ),
            audit=audit,
        )

        conn.commit()

        return {
            "ok": True,
            "code": "unlocked",
            "message": "账号锁定已经解除。",
            "result_status": "success",
            "user": safe_updated,
            "audit_written": True,
        }

    except Exception as error:
        return _error_result(
            conn,
            error=error,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=str(
                target_user_id
            ),
            target_label=target_label,
            before_data=safe_before,
            audit=audit,
        )


def reset_account_password(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    target_user_id: int,
    password: Any,
    must_change_password: bool = True,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action_key = (
        "account_password_reset"
    )

    action_label = (
        "重置系统账号密码"
    )

    actor = get_user_by_id(
        conn,
        int(actor_user_id),
    )

    target = get_user_by_id(
        conn,
        int(target_user_id),
    )

    safe_before = _safe_user(
        target
    )

    target_label = str(
        (
            target or {}
        ).get(
            "username"
        )
        or target_user_id
    )

    try:
        # Fail closed before input validation or write-lock acquisition.
        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        target = _require_target(
            conn,
            int(target_user_id),
        )

        target_label = str(
            target.get("username")
            or target_user_id
        )

        password = (
            validate_account_password(
                password,
                username=target_label,
            )
        )

        password_hash = (
            generate_password_hash(
                password,
                method="scrypt",
            )
        )

        if not check_password_hash(
            password_hash,
            password,
        ):
            raise RuntimeError(
                "密码哈希自检失败。"
            )

        _begin_write(
            conn
        )

        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        target = _require_target(
            conn,
            int(target_user_id),
        )

        safe_before = _safe_user(
            target
        )

        target_label = str(
            target.get("username")
            or target_user_id
        )

        cursor = conn.execute(
            """
            UPDATE v158_users
            SET
                password_hash=?,
                password_changed_at=
                    datetime(
                        'now',
                        'localtime'
                    ),
                must_change_password=?,
                failed_login_count=0,
                locked_until=NULL,
                last_failed_login_at=NULL,
                session_version=
                    session_version + 1,
                updated_at=datetime(
                    'now',
                    'localtime'
                )
            WHERE id=?
            """,
            (
                password_hash,
                (
                    1
                    if must_change_password
                    else 0
                ),
                int(target_user_id),
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "密码重置行数异常。"
            )

        updated = _require_target(
            conn,
            int(target_user_id),
        )

        safe_updated = _safe_user(
            updated
        )

        context = _audit_context(
            audit
        )

        record_login_event(
            conn,
            user_id=int(
                target_user_id
            ),
            username_snapshot=(
                target_label
            ),
            event_type=(
                "password_changed"
            ),
            result_status="success",
            reason_code=(
                "admin_password_reset"
            ),
            ip_address=(
                context["ip_address"]
            ),
            user_agent=(
                context["user_agent"]
            ),
            request_path=(
                context["request_path"]
            ),
            session_version=int(
                updated.get(
                    "session_version"
                )
                or 1
            ),
        )

        _record_account_action(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=str(
                target_user_id
            ),
            target_label=target_label,
            result_status="success",
            before_data=safe_before,
            after_data=safe_updated,
            reason=(
                "密码重置后，目标账号全部旧会话失效。"
            ),
            audit=audit,
        )

        conn.commit()

        return {
            "ok": True,
            "code": "password_reset",
            "message": (
                "密码已重置，目标账号旧会话已经失效。"
            ),
            "result_status": "success",
            "user": safe_updated,
            "sessions_invalidated": True,
            "audit_written": True,
        }

    except Exception as error:
        return _error_result(
            conn,
            error=error,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=str(
                target_user_id
            ),
            target_label=target_label,
            before_data=safe_before,
            audit=audit,
        )


def invalidate_account_sessions(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    target_user_id: int,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action_key = (
        "account_force_logout"
    )

    action_label = (
        "强制注销账号全部会话"
    )

    actor = get_user_by_id(
        conn,
        int(actor_user_id),
    )

    target = get_user_by_id(
        conn,
        int(target_user_id),
    )

    safe_before = _safe_user(
        target
    )

    target_label = str(
        (
            target or {}
        ).get(
            "username"
        )
        or target_user_id
    )

    try:
        # Fail closed before input validation or write-lock acquisition.
        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        _begin_write(
            conn
        )

        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        target = _require_target(
            conn,
            int(target_user_id),
        )

        safe_before = _safe_user(
            target
        )

        target_label = str(
            target.get("username")
            or target_user_id
        )

        cursor = conn.execute(
            """
            UPDATE v158_users
            SET
                session_version=
                    session_version + 1,
                updated_at=datetime(
                    'now',
                    'localtime'
                )
            WHERE id=?
            """,
            (
                int(target_user_id),
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "会话失效更新行数异常。"
            )

        updated = _require_target(
            conn,
            int(target_user_id),
        )

        safe_updated = _safe_user(
            updated
        )

        _record_account_action(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=str(
                target_user_id
            ),
            target_label=target_label,
            result_status="success",
            before_data=safe_before,
            after_data=safe_updated,
            reason=(
                "递增session_version，"
                "使目标账号全部旧会话失效。"
            ),
            audit=audit,
        )

        conn.commit()

        return {
            "ok": True,
            "code": "sessions_invalidated",
            "message": (
                "目标账号的全部旧会话已经失效。"
            ),
            "result_status": "success",
            "user": safe_updated,
            "sessions_invalidated": True,
            "audit_written": True,
        }

    except Exception as error:
        return _error_result(
            conn,
            error=error,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_id=str(
                target_user_id
            ),
            target_label=target_label,
            before_data=safe_before,
            audit=audit,
        )
