from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _function_source(
    path: Path,
    name: str,
) -> str:
    src = path.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(src)

    for node in tree.body:
        if (
            isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
            and node.name == name
        ):
            return (
                ast.get_source_segment(
                    src,
                    node,
                )
                or ""
            )

    raise AssertionError(
        f"function not found: {name}"
    )


def test_before_request_snapshots_registry_id_before_auth_validation():
    text = _function_source(
        ROOT / "app.py",
        "v158_authentication_before_request",
    )

    snapshot = text.index(
        "previous_registry_session_id"
    )

    validation = text.index(
        "validate_auth_session("
    )

    assert snapshot < validation


def test_before_request_idle_timeout_terminalizes_registry_only_when_enforced():
    text = _function_source(
        ROOT / "app.py",
        "v158_authentication_before_request",
    )

    assert (
        '== "idle_timeout"'
        in text
    )

    assert (
        "v155_session_registry_enforced()"
        in text
    )

    assert (
        "mark_current_session_expired("
        in text
    )

    assert (
        "previous_registry_session_id"
        in text
    )


def test_expiry_primitive_is_terminal_history_preserving():
    text = _function_source(
        ROOT
        / "services"
        / "v155_session_registry_service.py",
        "mark_current_session_expired",
    )

    assert "_begin_owned_write(conn)" in text
    assert "status='expired'" in text
    assert "revoke_reason='idle_timeout'" in text
    assert "revoked_by_user_id=NULL" in text
    assert "AND status='active'" in text

    normalized = " ".join(
        text.upper().split()
    )

    assert (
        "DELETE FROM V155_USER_SESSIONS"
        not in normalized
    )

    update_section = text.split(
        "UPDATE v155_user_sessions",
        1,
    )[1].split(
        '"""',
        1,
    )[0]

    assert (
        "session_version"
        not in update_section
    )


def test_normal_logout_semantics_remain_distinct():
    text = _function_source(
        ROOT
        / "services"
        / "v155_session_registry_service.py",
        "mark_current_session_logged_out",
    )

    assert "status='logged_out'" in text
    assert "revoke_reason='logout'" in text
    assert "status='expired'" not in text


def test_admin_revoke_semantics_remain_distinct():
    text = (
        ROOT
        / "services"
        / "v155_session_admin_service.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "revoke_reason='admin_single_revoke'"
        in text
    )
