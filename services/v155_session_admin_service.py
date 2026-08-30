from __future__ import annotations

import sqlite3

from datetime import (
    datetime,
    timezone,
)

from typing import (
    Any,
    Mapping,
)

from services.v158_auth_config import (
    v155_session_registry_enforced,
)

from services.v158_auth_store import (
    get_user_by_id,
    record_action_log,
)

from services.v158_account_admin_service import (
    invalidate_account_sessions,
)

from services.v155_session_registry_service import (
    DEFAULT_MAX_ACTIVE_SESSIONS,
    MAX_MAX_ACTIVE_SESSIONS,
    MIN_MAX_ACTIVE_SESSIONS,
    get_max_active_sessions,
    list_user_sessions,
)


class SessionAdminError(Exception):
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
            or "session_admin_error"
        )[:64]

        self.message = str(
            message
            or "会话管理操作失败。"
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


def _now_text() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )


def _table_exists(
    conn: sqlite3.Connection,
    table_name: str,
) -> bool:

    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE
            type='table'
            AND name=?
        LIMIT 1
        """,
        (
            str(table_name),
        ),
    ).fetchone()

    return (
        row is not None
    )


def session_registry_schema_ready(
    conn: sqlite3.Connection,
) -> bool:

    return all(
        _table_exists(
            conn,
            table_name,
        )
        for table_name
        in (
            "v155_user_sessions",
            "v155_user_session_policies",
        )
    )


def _safe_user(
    user,
) -> dict[str, Any] | None:

    if user is None:
        return None

    source = dict(user)

    return {
        key: source.get(key)
        for key in (
            "id",
            "username",
            "display_name",
            "role",
            "status",
            "session_version",
            "last_login_at",
            "last_login_ip",
        )
    }


def _get_target_user(
    conn: sqlite3.Connection,
    user_id: int,
) -> dict[str, Any]:

    user = get_user_by_id(
        conn,
        int(user_id),
    )

    safe = _safe_user(
        user
    )

    if safe is None:
        raise SessionAdminError(
            "target_user_not_found",
            "目标账号不存在。",
        )

    return safe


def _require_super_admin(
    conn: sqlite3.Connection,
    actor_user_id: int,
) -> dict[str, Any]:

    actor = _safe_user(
        get_user_by_id(
            conn,
            int(actor_user_id),
        )
    )

    if actor is None:
        raise SessionAdminError(
            "actor_not_found",
            "当前管理员账号不存在。",
        )

    if (
        str(
            actor.get("status")
            or ""
        )
        != "active"
        or str(
            actor.get("role")
            or ""
        )
        != "super_admin"
    ):
        raise SessionAdminError(
            "super_admin_required",
            "仅超级管理员可以管理登录设备和会话。",
        )

    return actor


def _audit_context(
    audit: Mapping[str, Any] | None,
) -> dict[str, str]:

    source = dict(
        audit
        or {}
    )

    method = str(
        source.get(
            "request_method"
        )
        or ""
    ).upper()[:10]

    if method not in {
        "",
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "CLI",
        "SYSTEM",
    }:
        method = ""

    return {
        "request_method": method,
        "request_path": str(
            source.get(
                "request_path"
            )
            or ""
        )[:500],
        "ip_address": str(
            source.get(
                "ip_address"
            )
            or ""
        )[:64],
        "user_agent": str(
            source.get(
                "user_agent"
            )
            or ""
        )[:1000],
    }


def _record_session_action(
    conn: sqlite3.Connection,
    *,
    actor: Mapping[str, Any],
    action_key: str,
    action_label: str,
    target_user: Mapping[str, Any],
    result_status: str,
    before_data=None,
    after_data=None,
    reason: str = "",
    audit: Mapping[str, Any] | None = None,
) -> None:

    context = _audit_context(
        audit
    )

    record_action_log(
        conn,
        user_id=int(
            actor["id"]
        ),
        username_snapshot=str(
            actor.get(
                "username"
            )
            or ""
        ),
        role_snapshot=str(
            actor.get(
                "role"
            )
            or ""
        ),
        action_key=str(
            action_key
        )[:100],
        action_label=str(
            action_label
        )[:200],
        target_type="user",
        target_id=str(
            target_user.get(
                "id"
            )
            or ""
        ),
        target_label=str(
            target_user.get(
                "username"
            )
            or target_user.get(
                "id"
            )
            or ""
        )[:300],
        result_status=(
            result_status
        ),
        before_data=(
            before_data
            if before_data
            is not None
            else {}
        ),
        after_data=(
            after_data
            if after_data
            is not None
            else {}
        ),
        reason=str(
            reason
            or ""
        )[:2000],
        request_method=(
            context[
                "request_method"
            ]
        ),
        request_path=(
            context[
                "request_path"
            ]
        ),
        ip_address=(
            context[
                "ip_address"
            ]
        ),
        user_agent=(
            context[
                "user_agent"
            ]
        ),
    )


def _begin_registry_write(
    conn: sqlite3.Connection,
) -> None:

    if conn.in_transaction:
        raise SessionAdminError(
            "external_transaction_not_allowed",
            "会话管理服务不接受外部未提交事务。",
            result_status="failure",
        )

    foreign_keys = int(
        conn.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]
    )

    if foreign_keys != 1:
        raise SessionAdminError(
            "foreign_keys_required",
            "会话管理写操作要求 foreign_keys=ON。",
            result_status="failure",
        )

    conn.execute(
        "BEGIN IMMEDIATE"
    )


def _require_registry_write_ready(
    conn: sqlite3.Connection,
) -> None:

    if not v155_session_registry_enforced():
        raise SessionAdminError(
            "registry_enforcement_disabled",
            "设备会话管理尚未正式启用。",
        )

    if not session_registry_schema_ready(
        conn
    ):
        raise SessionAdminError(
            "registry_schema_unavailable",
            "设备会话数据表尚未完成生产切换。",
            result_status="failure",
        )


def _safe_session_snapshot(
    conn: sqlite3.Connection,
    *,
    session_row_id: int,
    target_user_id: int,
) -> dict[str, Any] | None:

    row = conn.execute(
        """
        SELECT
            id,
            user_id,
            session_version,
            status,
            created_at,
            last_seen_at,
            expires_at,
            revoked_at,
            revoke_reason,
            revoked_by_user_id,
            login_ip,
            last_ip,
            user_agent,
            device_label
        FROM v155_user_sessions
        WHERE
            id=?
            AND user_id=?
        """,
        (
            int(session_row_id),
            int(target_user_id),
        ),
    ).fetchone()

    if row is None:
        return None

    columns = (
        "id",
        "user_id",
        "session_version",
        "status",
        "created_at",
        "last_seen_at",
        "expires_at",
        "revoked_at",
        "revoke_reason",
        "revoked_by_user_id",
        "login_ip",
        "last_ip",
        "user_agent",
        "device_label",
    )

    if isinstance(
        row,
        sqlite3.Row,
    ):
        return dict(row)

    return dict(
        zip(
            columns,
            tuple(row),
        )
    )


def _best_effort_failure_audit(
    conn: sqlite3.Connection,
    *,
    actor,
    action_key: str,
    action_label: str,
    target_user,
    error: Exception,
    audit: Mapping[str, Any] | None,
) -> None:

    if conn.in_transaction:
        conn.rollback()

    if (
        actor is None
        or target_user is None
    ):
        return

    result_status = (
        error.result_status
        if isinstance(
            error,
            SessionAdminError,
        )
        else "failure"
    )

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        _record_session_action(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_user=target_user,
            result_status=result_status,
            reason=str(error),
            audit=audit,
        )

        conn.commit()

    except Exception:
        if conn.in_transaction:
            conn.rollback()


def _error_result(
    error: Exception,
) -> dict[str, Any]:

    if isinstance(
        error,
        SessionAdminError,
    ):
        return {
            "ok": False,
            "code": error.code,
            "message": error.message,
            "result_status": (
                error.result_status
            ),
        }

    return {
        "ok": False,
        "code": (
            "session_admin_failure"
        ),
        "message": (
            "设备会话管理操作失败。"
        ),
        "result_status": "failure",
    }


def build_session_admin_report(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
) -> dict[str, Any]:

    _require_super_admin(
        conn,
        int(actor_user_id),
    )

    schema_ready = (
        session_registry_schema_ready(
            conn
        )
    )

    enforcement_enabled = (
        v155_session_registry_enforced()
    )

    rows = conn.execute(
        """
        SELECT
            id,
            username,
            display_name,
            role,
            status,
            session_version,
            last_login_at,
            last_login_ip
        FROM v158_users
        ORDER BY
            CASE role
                WHEN 'super_admin'
                THEN 1
                WHEN 'manager'
                THEN 2
                ELSE 3
            END,
            id
        """
    ).fetchall()

    accounts = []

    now_text = _now_text()

    for row in rows:
        user = dict(row)

        user_id = int(
            user["id"]
        )

        if schema_ready:
            max_sessions = int(
                get_max_active_sessions(
                    conn,
                    user_id,
                )
            )

            sessions = (
                list_user_sessions(
                    conn,
                    user_id=user_id,
                )
            )

            active_row = conn.execute(
                """
                SELECT COUNT(*)
                FROM v155_user_sessions
                WHERE
                    user_id=?
                    AND status='active'
                    AND session_version=?
                    AND expires_at>?
                """,
                (
                    user_id,
                    int(
                        user.get(
                            "session_version"
                        )
                        or 1
                    ),
                    now_text,
                ),
            ).fetchone()

            active_count = int(
                active_row[0]
                or 0
            )

        else:
            max_sessions = (
                DEFAULT_MAX_ACTIVE_SESSIONS
            )

            sessions = []
            active_count = 0

        accounts.append(
            {
                "user": user,
                "max_active_sessions": (
                    max_sessions
                ),
                "active_session_count": (
                    active_count
                ),
                "sessions": sessions,
            }
        )

    return {
        "registry_schema_ready": (
            schema_ready
        ),
        "registry_enforced": (
            enforcement_enabled
        ),
        "write_ready": (
            schema_ready
            and enforcement_enabled
        ),
        "default_max_active_sessions": (
            DEFAULT_MAX_ACTIVE_SESSIONS
        ),
        "min_max_active_sessions": (
            MIN_MAX_ACTIVE_SESSIONS
        ),
        "max_max_active_sessions": (
            MAX_MAX_ACTIVE_SESSIONS
        ),
        "accounts": accounts,
    }


def revoke_single_session(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    target_user_id: int,
    session_row_id: int,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:

    actor = None
    target = None

    action_key = (
        "session_revoke_single"
    )

    action_label = (
        "注销指定登录设备"
    )

    try:
        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        target = _get_target_user(
            conn,
            int(target_user_id),
        )

        _require_registry_write_ready(
            conn
        )

        if (
            int(session_row_id)
            <= 0
        ):
            raise SessionAdminError(
                "invalid_session_id",
                "会话编号无效。",
            )

        _begin_registry_write(
            conn
        )

        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        target = _get_target_user(
            conn,
            int(target_user_id),
        )

        before = (
            _safe_session_snapshot(
                conn,
                session_row_id=(
                    int(
                        session_row_id
                    )
                ),
                target_user_id=(
                    int(
                        target_user_id
                    )
                ),
            )
        )

        if before is None:
            raise SessionAdminError(
                "session_not_found",
                "目标会话不存在或不属于该账号。",
            )

        changed = False

        if (
            str(
                before.get(
                    "status"
                )
                or ""
            )
            == "active"
        ):
            cursor = conn.execute(
                """
                UPDATE v155_user_sessions
                SET
                    status='revoked',
                    revoked_at=?,
                    revoke_reason='admin_single_revoke',
                    revoked_by_user_id=?
                WHERE
                    id=?
                    AND user_id=?
                    AND status='active'
                """,
                (
                    _now_text(),
                    int(
                        actor_user_id
                    ),
                    int(
                        session_row_id
                    ),
                    int(
                        target_user_id
                    ),
                ),
            )

            if cursor.rowcount != 1:
                raise SessionAdminError(
                    "session_revoke_race",
                    "目标会话状态已经发生变化，请刷新后重试。",
                )

            changed = True

        after = (
            _safe_session_snapshot(
                conn,
                session_row_id=(
                    int(
                        session_row_id
                    )
                ),
                target_user_id=(
                    int(
                        target_user_id
                    )
                ),
            )
        )

        _record_session_action(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_user=target,
            result_status="success",
            before_data=before,
            after_data=after,
            reason=(
                "超级管理员注销指定登录设备。"
                if changed
                else (
                    "目标会话已经不是 active，"
                    "保持终态不重新激活。"
                )
            ),
            audit=audit,
        )

        conn.commit()

        return {
            "ok": True,
            "code": (
                "session_revoked"
                if changed
                else "session_already_inactive"
            ),
            "message": (
                "指定登录设备已注销。"
                if changed
                else "该会话已经失效。"
            ),
            "result_status": "success",
            "changed": changed,
        }

    except Exception as error:
        _best_effort_failure_audit(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_user=target,
            error=error,
            audit=audit,
        )

        return _error_result(
            error
        )


def set_session_policy(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    target_user_id: int,
    max_active_sessions: int,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:

    actor = None
    target = None

    action_key = (
        "session_policy_update"
    )

    action_label = (
        "修改账号同时在线设备上限"
    )

    try:
        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        target = _get_target_user(
            conn,
            int(target_user_id),
        )

        _require_registry_write_ready(
            conn
        )

        try:
            limit = int(
                max_active_sessions
            )
        except (
            TypeError,
            ValueError,
        ):
            raise SessionAdminError(
                "invalid_session_limit",
                "同时在线设备上限必须是整数。",
            )

        if not (
            MIN_MAX_ACTIVE_SESSIONS
            <= limit
            <= MAX_MAX_ACTIVE_SESSIONS
        ):
            raise SessionAdminError(
                "invalid_session_limit",
                (
                    "同时在线设备上限必须在 "
                    f"{MIN_MAX_ACTIVE_SESSIONS}"
                    " 至 "
                    f"{MAX_MAX_ACTIVE_SESSIONS}"
                    " 之间。"
                ),
            )

        previous_limit = int(
            get_max_active_sessions(
                conn,
                int(
                    target_user_id
                ),
            )
        )

        _begin_registry_write(
            conn
        )

        actor = _require_super_admin(
            conn,
            int(actor_user_id),
        )

        target = _get_target_user(
            conn,
            int(target_user_id),
        )

        conn.execute(
            """
            INSERT INTO
                v155_user_session_policies (
                    user_id,
                    max_active_sessions,
                    updated_at,
                    updated_by_user_id
                )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(user_id)
            DO UPDATE SET
                max_active_sessions=
                    excluded.max_active_sessions,
                updated_at=
                    excluded.updated_at,
                updated_by_user_id=
                    excluded.updated_by_user_id
            """,
            (
                int(
                    target_user_id
                ),
                limit,
                _now_text(),
                int(
                    actor_user_id
                ),
            ),
        )

        _record_session_action(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_user=target,
            result_status="success",
            before_data={
                "max_active_sessions": (
                    previous_limit
                ),
            },
            after_data={
                "max_active_sessions": (
                    limit
                ),
            },
            reason=(
                "修改账号同时在线设备上限；"
                "降低上限不会自动踢出已有设备。"
            ),
            audit=audit,
        )

        conn.commit()

        return {
            "ok": True,
            "code": (
                "session_policy_updated"
            ),
            "message": (
                "同时在线设备上限已更新。"
            ),
            "result_status": "success",
            "max_active_sessions": (
                limit
            ),
        }

    except Exception as error:
        _best_effort_failure_audit(
            conn,
            actor=actor,
            action_key=action_key,
            action_label=action_label,
            target_user=target,
            error=error,
            audit=audit,
        )

        return _error_result(
            error
        )


def revoke_all_user_sessions(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    target_user_id: int,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:

    try:
        _require_super_admin(
            conn,
            int(actor_user_id),
        )

        _get_target_user(
            conn,
            int(target_user_id),
        )

        _require_registry_write_ready(
            conn
        )

    except Exception as error:
        return _error_result(
            error
        )

    # The existing account-wide invalidation path owns
    # the transaction. Under registry enforcement it
    # increments session_version and calls the frozen
    # non-owning registry revoke primitive inside the
    # same transaction.
    return invalidate_account_sessions(
        conn,
        actor_user_id=int(
            actor_user_id
        ),
        target_user_id=int(
            target_user_id
        ),
        audit=audit,
    )
