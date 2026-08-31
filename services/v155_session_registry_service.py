from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


DEFAULT_MAX_ACTIVE_SESSIONS = 2
MIN_MAX_ACTIVE_SESSIONS = 1
MAX_MAX_ACTIVE_SESSIONS = 10

SESSION_ID_BYTES = 32

LAST_SEEN_MIN_UPDATE_SECONDS = 300


class SessionRegistryError(RuntimeError):
    pass


class ForeignKeysRequired(
    SessionRegistryError
):
    pass


class TransactionOwnershipError(
    SessionRegistryError
):
    pass


class SessionLimitExceeded(
    SessionRegistryError
):
    pass


class InvalidSessionPolicy(
    SessionRegistryError
):
    pass


@dataclass(frozen=True)
class SessionCreationResult:
    session_row_id: int
    raw_session_id: str
    session_key_hash: str
    max_active_sessions: int


@dataclass(frozen=True)
class SessionValidationResult:
    valid: bool
    reason: str
    session_row_id: Optional[int] = None
    status: Optional[str] = None


def hash_session_identifier(
    raw_session_id: str,
) -> str:
    if not isinstance(
        raw_session_id,
        str,
    ):
        raise TypeError(
            "raw_session_id must be str"
        )

    if not raw_session_id:
        raise ValueError(
            "raw_session_id must not be empty"
        )

    return hashlib.sha256(
        raw_session_id.encode("utf-8")
    ).hexdigest()


def _coerce_datetime(
    value=None,
) -> datetime:
    if value is None:
        return datetime.now(
            timezone.utc
        )

    if isinstance(
        value,
        datetime,
    ):
        dt = value

    elif isinstance(
        value,
        str,
    ):
        raw = value.strip()

        if raw.endswith("Z"):
            raw = (
                raw[:-1]
                + "+00:00"
            )

        dt = datetime.fromisoformat(
            raw
        )

    else:
        raise TypeError(
            "datetime value must be "
            "datetime, str, or None"
        )

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(
        timezone.utc
    )


def _timestamp(
    value=None,
) -> str:
    return (
        _coerce_datetime(value)
        .strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )


def _require_foreign_keys(
    conn: sqlite3.Connection,
) -> None:
    value = int(
        conn.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]
    )

    if value != 1:
        raise ForeignKeysRequired(
            "session registry mutations "
            "require PRAGMA foreign_keys=ON"
        )


def _begin_owned_write(
    conn: sqlite3.Connection,
) -> None:
    if conn.in_transaction:
        raise TransactionOwnershipError(
            "nested transaction ownership "
            "is not allowed"
        )

    _require_foreign_keys(conn)

    conn.execute(
        "BEGIN IMMEDIATE"
    )


def get_max_active_sessions(
    conn: sqlite3.Connection,
    user_id: int,
) -> int:
    row = conn.execute(
        """
        SELECT max_active_sessions
        FROM v155_user_session_policies
        WHERE user_id=?
        """,
        (int(user_id),),
    ).fetchone()

    if row is None:
        return (
            DEFAULT_MAX_ACTIVE_SESSIONS
        )

    value = int(row[0])

    if not (
        MIN_MAX_ACTIVE_SESSIONS
        <= value
        <= MAX_MAX_ACTIVE_SESSIONS
    ):
        raise InvalidSessionPolicy(
            "stored session policy "
            "is outside allowed range"
        )

    return value


def set_max_active_sessions(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    max_active_sessions: int,
    updated_by_user_id: Optional[int],
    now=None,
) -> None:
    value = int(
        max_active_sessions
    )

    if not (
        MIN_MAX_ACTIVE_SESSIONS
        <= value
        <= MAX_MAX_ACTIVE_SESSIONS
    ):
        raise InvalidSessionPolicy(
            "max_active_sessions "
            "must be between 1 and 10"
        )

    _begin_owned_write(conn)

    try:
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
                int(user_id),
                value,
                _timestamp(now),
                (
                    int(updated_by_user_id)
                    if updated_by_user_id
                    is not None
                    else None
                ),
            ),
        )

        conn.commit()

    except Exception:
        if conn.in_transaction:
            conn.rollback()

        raise


def create_registered_session(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    session_version: int,
    expires_at,
    login_ip: str = "",
    user_agent: str = "",
    device_label: str = "",
    now=None,
) -> SessionCreationResult:
    uid = int(user_id)
    version = int(session_version)

    if uid <= 0:
        raise ValueError(
            "user_id must be positive"
        )

    if version < 1:
        raise ValueError(
            "session_version must be >= 1"
        )

    now_dt = _coerce_datetime(now)
    expires_dt = _coerce_datetime(
        expires_at
    )

    if expires_dt <= now_dt:
        raise ValueError(
            "expires_at must be future"
        )

    now_text = _timestamp(now_dt)
    expires_text = _timestamp(
        expires_dt
    )

    _begin_owned_write(conn)

    try:
        limit = get_max_active_sessions(
            conn,
            uid,
        )

        active_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM v155_user_sessions
                WHERE user_id=?
                  AND status='active'
                  AND session_version=?
                  AND expires_at>?
                """,
                (
                    uid,
                    version,
                    now_text,
                ),
            ).fetchone()[0]
        )

        if active_count >= limit:
            raise SessionLimitExceeded(
                "maximum active sessions "
                "reached"
            )

        raw_session_id = (
            secrets.token_urlsafe(
                SESSION_ID_BYTES
            )
        )

        session_hash = (
            hash_session_identifier(
                raw_session_id
            )
        )

        cursor = conn.execute(
            """
            INSERT INTO v155_user_sessions (
                user_id,
                session_key_hash,
                session_version,
                status,
                created_at,
                last_seen_at,
                expires_at,
                login_ip,
                last_ip,
                user_agent,
                device_label
            )
            VALUES (
                ?, ?, ?, 'active',
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                uid,
                session_hash,
                version,
                now_text,
                now_text,
                expires_text,
                str(login_ip or ""),
                str(login_ip or ""),
                str(user_agent or ""),
                str(device_label or ""),
            ),
        )

        row_id = int(
            cursor.lastrowid
        )

        conn.commit()

        return SessionCreationResult(
            session_row_id=row_id,
            raw_session_id=raw_session_id,
            session_key_hash=session_hash,
            max_active_sessions=limit,
        )

    except Exception:
        if conn.in_transaction:
            conn.rollback()

        raise


def validate_registered_session(
    conn: sqlite3.Connection,
    *,
    raw_session_id: str,
    user_id: int,
    current_session_version: int,
    now=None,
) -> SessionValidationResult:
    if not raw_session_id:
        return SessionValidationResult(
            valid=False,
            reason="missing_session_id",
        )

    session_hash = (
        hash_session_identifier(
            raw_session_id
        )
    )

    row = conn.execute(
        """
        SELECT
            id,
            user_id,
            session_version,
            status,
            expires_at
        FROM v155_user_sessions
        WHERE session_key_hash=?
        """,
        (session_hash,),
    ).fetchone()

    if row is None:
        return SessionValidationResult(
            valid=False,
            reason="not_found",
        )

    row_id = int(row[0])
    stored_user_id = int(row[1])
    stored_version = int(row[2])
    status = str(row[3])
    expires_at = row[4]

    if stored_user_id != int(user_id):
        return SessionValidationResult(
            valid=False,
            reason="user_mismatch",
            session_row_id=row_id,
            status=status,
        )

    if status != "active":
        return SessionValidationResult(
            valid=False,
            reason="not_active",
            session_row_id=row_id,
            status=status,
        )

    if (
        stored_version
        != int(
            current_session_version
        )
    ):
        return SessionValidationResult(
            valid=False,
            reason=(
                "session_version_mismatch"
            ),
            session_row_id=row_id,
            status=status,
        )

    if (
        _coerce_datetime(
            expires_at
        )
        <= _coerce_datetime(now)
    ):
        return SessionValidationResult(
            valid=False,
            reason="expired",
            session_row_id=row_id,
            status=status,
        )

    return SessionValidationResult(
        valid=True,
        reason="ok",
        session_row_id=row_id,
        status=status,
    )


def mark_current_session_expired(
    conn: sqlite3.Connection,
    *,
    raw_session_id: str,
    user_id: int,
    now=None,
) -> bool:
    """
    Terminalize the caller's matching active registry
    session after authentication idle timeout.

    This owns its write transaction and never changes
    session_version or deletes registry history.
    """
    session_hash = (
        hash_session_identifier(
            raw_session_id
        )
    )

    _begin_owned_write(conn)

    try:
        cursor = conn.execute(
            """
            UPDATE v155_user_sessions
            SET
                status='expired',
                revoked_at=?,
                revoke_reason='idle_timeout',
                revoked_by_user_id=NULL
            WHERE session_key_hash=?
              AND user_id=?
              AND status='active'
            """,
            (
                _timestamp(now),
                session_hash,
                int(user_id),
            ),
        )

        changed = (
            cursor.rowcount > 0
        )

        conn.commit()

        return changed

    except Exception:
        if conn.in_transaction:
            conn.rollback()

        raise


def mark_current_session_logged_out(
    conn: sqlite3.Connection,
    *,
    raw_session_id: str,
    user_id: int,
    now=None,
) -> bool:
    session_hash = (
        hash_session_identifier(
            raw_session_id
        )
    )

    _begin_owned_write(conn)

    try:
        cursor = conn.execute(
            """
            UPDATE v155_user_sessions
            SET
                status='logged_out',
                revoked_at=?,
                revoke_reason='logout',
                revoked_by_user_id=NULL
            WHERE session_key_hash=?
              AND user_id=?
              AND status='active'
            """,
            (
                _timestamp(now),
                session_hash,
                int(user_id),
            ),
        )

        changed = (
            cursor.rowcount > 0
        )

        conn.commit()

        return changed

    except Exception:
        if conn.in_transaction:
            conn.rollback()

        raise


def revoke_session_by_id(
    conn: sqlite3.Connection,
    *,
    session_row_id: int,
    target_user_id: int,
    actor_user_id: Optional[int],
    reason: str,
    now=None,
) -> bool:
    _begin_owned_write(conn)

    try:
        cursor = conn.execute(
            """
            UPDATE v155_user_sessions
            SET
                status='revoked',
                revoked_at=?,
                revoke_reason=?,
                revoked_by_user_id=?
            WHERE id=?
              AND user_id=?
              AND status='active'
            """,
            (
                _timestamp(now),
                str(reason or "admin_revoke"),
                (
                    int(actor_user_id)
                    if actor_user_id
                    is not None
                    else None
                ),
                int(session_row_id),
                int(target_user_id),
            ),
        )

        changed = (
            cursor.rowcount > 0
        )

        conn.commit()

        return changed

    except Exception:
        if conn.in_transaction:
            conn.rollback()

        raise



def revoke_all_registry_sessions(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    actor_user_id: Optional[int],
    reason: str,
    now=None,
) -> int:
    """
    Standalone registry-only revocation.

    This wrapper owns its transaction.
    """
    _begin_owned_write(conn)

    try:
        count = (
            revoke_all_registry_sessions_in_transaction(
                conn,
                user_id=user_id,
                actor_user_id=actor_user_id,
                reason=reason,
                now=now,
            )
        )

        conn.commit()
        return count

    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise



def touch_registered_session(
    conn: sqlite3.Connection,
    *,
    raw_session_id: str,
    user_id: int,
    last_ip: str = "",
    now=None,
) -> bool:
    session_hash = (
        hash_session_identifier(
            raw_session_id
        )
    )

    now_dt = _coerce_datetime(now)

    _begin_owned_write(conn)

    try:
        row = conn.execute(
            """
            SELECT last_seen_at
            FROM v155_user_sessions
            WHERE session_key_hash=?
              AND user_id=?
              AND status='active'
            """,
            (
                session_hash,
                int(user_id),
            ),
        ).fetchone()

        if row is None:
            conn.commit()
            return False

        previous = (
            _coerce_datetime(
                row[0]
            )
        )

        elapsed = (
            now_dt - previous
        ).total_seconds()

        if (
            elapsed
            < LAST_SEEN_MIN_UPDATE_SECONDS
        ):
            conn.commit()
            return False

        cursor = conn.execute(
            """
            UPDATE v155_user_sessions
            SET
                last_seen_at=?,
                last_ip=?
            WHERE session_key_hash=?
              AND user_id=?
              AND status='active'
            """,
            (
                _timestamp(now_dt),
                str(last_ip or ""),
                session_hash,
                int(user_id),
            ),
        )

        changed = (
            cursor.rowcount > 0
        )

        conn.commit()

        return changed

    except Exception:
        if conn.in_transaction:
            conn.rollback()

        raise


def list_user_sessions(
    conn: sqlite3.Connection,
    *,
    user_id: int,
) -> list[dict]:
    rows = conn.execute(
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
        WHERE user_id=?
        ORDER BY
            created_at DESC,
            id DESC
        """,
        (int(user_id),),
    ).fetchall()

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

    return [
        dict(
            zip(
                columns,
                tuple(row),
            )
        )
        for row in rows
    ]

def revoke_all_registry_sessions_in_transaction(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    actor_user_id: Optional[int],
    reason: str,
    now=None,
) -> int:
    """
    Caller-owned transaction primitive.

    No BEGIN, COMMIT, or ROLLBACK is performed here.
    """
    if not conn.in_transaction:
        raise TransactionOwnershipError(
            "caller-owned transaction required"
        )

    _require_foreign_keys(conn)

    cursor = conn.execute(
        """
        UPDATE v155_user_sessions
        SET
            status='revoked',
            revoked_at=?,
            revoke_reason=?,
            revoked_by_user_id=?
        WHERE user_id=?
          AND status='active'
        """,
        (
            _timestamp(now),
            str(
                reason
                or "account_invalidation"
            ),
            (
                int(actor_user_id)
                if actor_user_id
                is not None
                else None
            ),
            int(user_id),
        ),
    )

    return int(cursor.rowcount)
