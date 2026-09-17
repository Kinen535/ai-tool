from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ACCOUNT_SERVICE = ROOT / "services" / "v158_account_admin_service.py"
ACCOUNT_TEMPLATE = ROOT / "templates" / "security_accounts.html"
ACCESS_TEMPLATE = ROOT / "templates" / "security_access_center.html"
SESSION_TEMPLATE = ROOT / "templates" / "security_sessions.html"
CONSOLE_TEMPLATE = ROOT / "templates" / "security_console.html"


def _text(path: Path) -> str:
    return path.read_text(
        encoding="utf-8",
        errors="strict",
    )


def test_zero_memberships_contract_is_exposed_by_account_model():
    source = _text(ACCOUNT_SERVICE)
    assert "memberships" in source, (
        "account read model must expose memberships=[]"
    )


def test_one_membership_contract_uses_account_membership_collection():
    source = _text(ACCOUNT_SERVICE)
    template = _text(ACCOUNT_TEMPLATE)

    assert "memberships" in source
    assert "user.memberships" in template


def test_multiple_memberships_are_rendered_as_a_collection():
    template = _text(ACCOUNT_TEMPLATE)

    assert (
        "{% for membership in user.memberships %}"
        in template
    )

    assert "user.memberships[0]" not in template


def test_membership_object_exposes_frozen_canonical_fields():
    source = _text(ACCOUNT_SERVICE)

    required = {
        "membership_id",
        "workspace_id",
        "workspace_name",
        "membership_status",
        "workspace_role_id",
        "workspace_role_key",
        "workspace_role_name",
        "workspace_role_status",
    }

    missing = sorted(
        field
        for field in required
        if field not in source
    )

    assert not missing, (
        f"missing canonical membership fields: {missing}"
    )


def test_memberships_use_frozen_deterministic_order_contract():
    source = _text(ACCOUNT_SERVICE)

    assert "casefold()" in source
    assert "workspace_name" in source
    assert "membership_id" in source


def test_account_history_uses_v158_action_logs():
    source = _text(ACCOUNT_SERVICE)

    assert "v158_action_logs" in source


def test_account_history_uses_user_target_type():
    source = _text(ACCOUNT_SERVICE)

    assert (
        "target_type='user'" in source
        or 'target_type="user"' in source
        or "target_type = 'user'" in source
        or 'target_type = "user"' in source
    )


def test_account_history_uses_target_id_for_displayed_account():
    source = _text(ACCOUNT_SERVICE)

    assert "target_id" in source
    assert "recent_actions" in source


def test_account_history_does_not_present_actor_as_target():
    source = _text(ACCOUNT_SERVICE)

    assert "user_id=actor_id" in source
    assert 'target_type="user"' in source
    assert "target_id=str(" in source


def test_account_history_is_bound_to_each_account_detail():
    template = _text(ACCOUNT_TEMPLATE)

    assert "user.recent_actions" in template


def test_account_detail_row_uses_frozen_colspan():
    template = _text(ACCOUNT_TEMPLATE)

    assert 'colspan="11"' in template


def test_account_detail_row_is_inside_user_loop():
    template = _text(ACCOUNT_TEMPLATE)

    loop_start = template.find(
        "{% for user in report.users %}"
    )

    loop_end = template.find(
        "{% endfor %}",
        loop_start,
    )

    detail = template.find(
        'colspan="11"',
        loop_start,
    )

    assert loop_start >= 0
    assert loop_end > loop_start
    assert loop_start < detail < loop_end


def test_zero_membership_state_is_explicit():
    template = _text(ACCOUNT_TEMPLATE)

    assert (
        "当前账号尚未加入任何 Workspace"
        in template
    )


def test_permission_deeplink_uses_exact_membership_id():
    template = _text(ACCOUNT_TEMPLATE)

    assert "v155_security_access_center" in template
    assert "membership.membership_id" in template


def test_account_page_links_to_exact_session_anchor():
    template = _text(ACCOUNT_TEMPLATE)

    assert "v155_security_sessions" in template
    assert "#account-" in template
    assert "user.id" in template


def test_permission_page_no_longer_claims_read_only_audit_view():
    template = _text(ACCESS_TEMPLATE)

    assert "只读审计视图" not in template


def test_permission_page_distinguishes_frozen_permission_states():
    template = _text(ACCESS_TEMPLATE)

    required_labels = {
        "角色基线权限",
        "单独授予",
        "单独禁止",
        "最终有效权限",
    }

    missing = sorted(
        label
        for label in required_labels
        if label not in template
    )

    assert not missing, (
        f"missing permission-state labels: {missing}"
    )


def test_session_page_has_exact_account_anchor():
    template = _text(SESSION_TEMPLATE)

    assert (
        'id="account-{{ user.id }}"'
        in template
    )


def test_session_write_ready_guard_remains_and_a6_copy_is_removed():
    template = _text(SESSION_TEMPLATE)

    assert "if not report.write_ready" in template

    assert "A6 生产切换前状态" not in template

    assert "会话写操作将在正式切换后开放" not in template


def test_security_console_keeps_account_and_operational_security_entries():
    template = _text(CONSOLE_TEMPLATE)

    assert "v158_security_accounts" in template

    operational_signals = (
        "审计",
        "安全日志",
        "清理",
        "Nginx",
        "闸门",
    )

    assert any(
        signal in template
        for signal in operational_signals
    )



def test_account_service_exposes_unified_configuration_summary_contract():
    source = _text(ACCOUNT_SERVICE)

    required = {
        "configuration_summary",
        "membership_count",
        "permission_override_count",
        "max_active_sessions",
        "active_session_count",
        "v155_membership_permission_overrides",
        "v155_user_session_policies",
        "v155_user_sessions",
        "DEFAULT_MAX_ACTIVE_SESSIONS",
        "get_max_active_sessions",
    }

    missing = sorted(
        marker
        for marker in required
        if marker not in source
    )

    assert not missing, (
        "missing account configuration "
        f"summary markers: {missing}"
    )


def test_account_summary_keeps_safe_session_dependency_direction():
    source = _text(ACCOUNT_SERVICE)

    assert (
        "v155_session_admin_service"
        not in source
    )

    assert (
        "v155_session_registry_service"
        in source
    )

    assert (
        "status='active'"
        in source
    )

    assert (
        "datetime(expires_at)"
        in source
    )


def test_account_page_renders_subaccount_configuration_summary():
    template = _text(ACCOUNT_TEMPLATE)

    required = {
        "子账号配置摘要",
        "工作区数量",
        "个性权限覆盖",
        "最大在线设备",
        "当前在线设备",
        "user.configuration_summary.membership_count",
        "user.configuration_summary.permission_override_count",
        "user.configuration_summary.max_active_sessions",
        "user.configuration_summary.active_session_count",
    }

    missing = sorted(
        marker
        for marker in required
        if marker not in template
    )

    assert not missing, (
        "missing subaccount configuration "
        f"UI markers: {missing}"
    )


def test_account_page_removes_obsolete_pending_capability_copy():
    template = _text(ACCOUNT_TEMPLATE)

    assert (
        "仍将在后续阶段逐项接入和验收。"
        not in template
    )

    assert (
        "首次登录强制改密流程尚未开放"
        in template
    )
