from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

from services.v155_rbac_workspace_resolver import (
    resolve_default_access_context,
)


ACCESS_CONTEXT_ATTRIBUTE = (
    "v155_access_context"
)


def _extract_user_id(
    current_user: Mapping[str, Any] | None,
) -> int | None:
    """
    Extract authenticated user id only.

    Deliberately ignores legacy role information.
    Workspace role and permissions must be resolved
    from the RBAC tables, not trusted from session data.
    """

    if not isinstance(
        current_user,
        Mapping,
    ):
        return None

    try:
        user_id = int(
            current_user.get(
                "id"
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if user_id <= 0:
        return None

    return user_id


def _open_read_only_connection(
    database_path: str | Path,
) -> sqlite3.Connection:
    """
    Open an explicitly read-only SQLite connection.
    """

    path = Path(
        database_path
    ).resolve()

    conn = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
        timeout=15,
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA query_only=ON"
    )

    conn.execute(
        "PRAGMA busy_timeout=15000"
    )

    return conn


def build_request_access_context(
    database_path: str | Path,
    current_user: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Convert authenticated user identity into
    Workspace/RBAC access context.

    Fail closed:
    - unauthenticated -> None
    - malformed user id -> None
    - database unavailable -> None
    - invalid Workspace/RBAC relationship -> None

    This function does not:
    - abort requests
    - redirect
    - mutate Flask session
    - trust legacy role
    - write to SQLite
    """

    user_id = _extract_user_id(
        current_user
    )

    if user_id is None:
        return None

    try:
        conn = (
            _open_read_only_connection(
                database_path
            )
        )
    except sqlite3.Error:
        return None

    try:
        try:
            return (
                resolve_default_access_context(
                    conn,
                    user_id,
                )
            )
        except sqlite3.Error:
            return None
    finally:
        conn.close()


def populate_request_access_context(
    flask_g: Any,
    database_path: str | Path,
    current_user: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Populate Flask g-like object with RBAC context.

    No authorization decision is made here.
    """

    context = (
        build_request_access_context(
            database_path,
            current_user,
        )
    )

    setattr(
        flask_g,
        ACCESS_CONTEXT_ATTRIBUTE,
        context,
    )

    return context
