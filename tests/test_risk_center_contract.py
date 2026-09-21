from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from flask import g
from jinja2 import Environment, meta

import app as app_module


EXPECTED_TEMPLATE_SHA256 = (
    "56f211fbeb6111729274f85e21975b1432c4b91ec3eca82e2fed2962957c12f8"
)

VALID_REASONS = (
    "活跃不足",
    "长期低贡献",
    "持续下滑",
    "连续停滞",
)

REQUIRED_CONTRACT_IDS = (
    "AUTH_PROTECTED",
    "WORKSPACE_BOUNDARY",
    "LATEST_NON_DELETED_SNAPSHOT",
    "CLEAR_TO_CLEANUP",
    "DANGER_WARNING_TO_OBSERVE",
    "PROTECTED_TO_PROTECTED",
    "RISK_RATE",
    "FOUR_REASON_FILTERS",
    "INVALID_REASON_SAFE",
    "TEMPLATE_CONTEXT",
    "NO_CROSS_BATTLE_LEAK",
    "TEMPLATE_HASH_UNCHANGED",
)


def _risk_view():
    return inspect.unwrap(app_module.risk_center)


def _risk_source():
    return textwrap.dedent(
        inspect.getsource(_risk_view())
    )


def _default_rows():
    return [
        {
            "member_name": "clear_member",
            "group_name": "A",
            "av": 10,
            "bs": 20,
            "identity_score": 10,
            "risk_level": "clear",
            "risk_reason": "长期低贡献｜活跃不足",
            "role_tag": "member",
            "is_protected": 0,
        },
        {
            "member_name": "danger_member",
            "group_name": "A",
            "av": 30,
            "bs": 40,
            "identity_score": 20,
            "risk_level": "danger",
            "risk_reason": "持续下滑",
            "role_tag": "member",
            "is_protected": 0,
        },
        {
            "member_name": "warning_member",
            "group_name": "B",
            "av": 50,
            "bs": 60,
            "identity_score": 30,
            "risk_level": "warning",
            "risk_reason": "连续停滞7期",
            "role_tag": "member",
            "is_protected": 0,
        },
        {
            "member_name": "protected_member",
            "group_name": "B",
            "av": 80,
            "bs": 80,
            "identity_score": 90,
            "risk_level": "protected",
            "risk_reason": "高贡献保护",
            "role_tag": "core",
            "is_protected": 1,
        },
        {
            "member_name": "safe_member",
            "group_name": "C",
            "av": 90,
            "bs": 90,
            "identity_score": 70,
            "risk_level": "safe",
            "risk_reason": "高速成长",
            "role_tag": "member",
            "is_protected": 0,
        },
    ]


class _Result:
    def __init__(self, *, one=None, many=None):
        self._one = one
        self._many = list(many or [])

    def fetchone(self):
        return self._one

    def fetchall(self):
        return list(self._many)


class _FakeConn:
    def __init__(
        self,
        *,
        rows=None,
        battle_exists=True,
        latest="2026-09-21 07:34:50",
    ):
        self.rows = list(
            _default_rows()
            if rows is None
            else rows
        )
        self.battle_exists = battle_exists
        self.latest = latest
        self.calls = []
        self.closed = False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        params = tuple(params)

        self.calls.append(
            (normalized, params)
        )

        if "SELECT id FROM battles" in normalized:
            assert params == (6,)
            return _Result(
                one=(
                    {"id": 6}
                    if self.battle_exists
                    else None
                )
            )

        if "SELECT MAX(snapshot_time)" in normalized:
            assert "WHERE battle_id = ?" in normalized
            assert "is_deleted = 0" in normalized
            assert params == (6,)
            return _Result(
                one=(self.latest,)
            )

        if "FROM player_records" in normalized:
            assert "WHERE battle_id = ?" in normalized
            assert "snapshot_time = ?" in normalized
            assert "is_deleted = 0" in normalized
            assert params == (
                6,
                self.latest,
            )
            return _Result(
                many=self.rows
            )

        raise AssertionError(
            f"Unexpected SQL: {normalized}"
        )

    def close(self):
        self.closed = True


def _run_risk(
    monkeypatch,
    *,
    reason=None,
    rows=None,
    battle_exists=True,
):
    conn = _FakeConn(
        rows=rows,
        battle_exists=battle_exists,
    )

    rendered = {}
    flashes = []
    resolver_seen = {}
    access_context = object()

    def fake_resolver(value):
        resolver_seen["value"] = value
        return SimpleNamespace(
            current_battle_id=6
        )

    def fake_render(template_name, **context):
        rendered["template"] = template_name
        rendered["context"] = context
        return "RISK_RENDERED"

    def fake_flash(message, category=None):
        flashes.append(
            (str(message), category)
        )

    monkeypatch.setattr(
        app_module,
        "resolve_workspace_data_boundary",
        fake_resolver,
    )
    monkeypatch.setattr(
        app_module,
        "get_conn",
        lambda: conn,
    )
    monkeypatch.setattr(
        app_module,
        "render_template",
        fake_render,
    )
    monkeypatch.setattr(
        app_module,
        "flash",
        fake_flash,
    )

    path = "/risk"

    if reason is not None:
        path += "?reason=" + quote(
            reason,
            safe="",
        )

    with app_module.app.test_request_context(
        path
    ):
        g.v155_access_context = access_context

        response = _risk_view()()

    return {
        "response": response,
        "conn": conn,
        "rendered": rendered,
        "flashes": flashes,
        "resolver_seen": resolver_seen,
        "access_context": access_context,
    }


def test_risk_remains_authentication_protected():
    client = app_module.app.test_client()

    response = client.get(
        "/risk",
        follow_redirects=False,
    )

    assert response.status_code == 302

    location = response.headers.get(
        "Location",
        "",
    )

    assert "/login" in location
    assert "next=/risk" in location


def test_workspace_latest_snapshot_and_population_contract(
    monkeypatch,
):
    result = _run_risk(monkeypatch)

    assert result["response"] == "RISK_RENDERED"
    assert (
        result["resolver_seen"]["value"]
        is result["access_context"]
    )

    conn = result["conn"]

    assert conn.closed is True

    battle_calls = [
        item
        for item in conn.calls
        if "SELECT id FROM battles" in item[0]
    ]

    latest_calls = [
        item
        for item in conn.calls
        if "SELECT MAX(snapshot_time)" in item[0]
    ]

    player_calls = [
        item
        for item in conn.calls
        if "FROM player_records" in item[0]
        and "MAX(snapshot_time)" not in item[0]
    ]

    assert len(battle_calls) == 1
    assert battle_calls[0][1] == (6,)

    assert len(latest_calls) == 1
    assert latest_calls[0][1] == (6,)
    assert "is_deleted = 0" in latest_calls[0][0]

    assert len(player_calls) == 1
    assert player_calls[0][1] == (
        6,
        "2026-09-21 07:34:50",
    )
    assert "snapshot_time = ?" in player_calls[0][0]
    assert "is_deleted = 0" in player_calls[0][0]

    rendered = result["rendered"]

    assert rendered["template"] == "risk_center.html"

    context = rendered["context"]

    assert [
        row["member_name"]
        for row in context["high_risk"]
    ] == [
        "clear_member",
    ]

    assert [
        row["member_name"]
        for row in context["warning_risk"]
    ] == [
        "danger_member",
        "warning_member",
    ]

    assert [
        row["member_name"]
        for row in context["protected"]
    ] == [
        "protected_member",
    ]

    assert [
        row["member_name"]
        for row in context["cleanup_members"]
    ] == [
        "clear_member",
    ]

    assert [
        row["member_name"]
        for row in context["observe_members"]
    ] == [
        "danger_member",
        "warning_member",
    ]

    assert [
        row["member_name"]
        for row in context["protected_members"]
    ] == [
        "protected_member",
    ]

    assert context["risk_rate"] == 60.0

    assert context["risk_stats"] == {
        "活跃不足": 1,
        "长期低贡献": 1,
        "持续下滑": 1,
        "连续停滞": 1,
    }

    assert context["selected_reason"] == ""


@pytest.mark.parametrize(
    ("reason", "cleanup_names", "observe_names"),
    [
        (
            "活跃不足",
            ["clear_member"],
            [],
        ),
        (
            "长期低贡献",
            ["clear_member"],
            [],
        ),
        (
            "持续下滑",
            [],
            ["danger_member"],
        ),
        (
            "连续停滞",
            [],
            ["warning_member"],
        ),
    ],
)
def test_four_valid_reason_filters(
    monkeypatch,
    reason,
    cleanup_names,
    observe_names,
):
    result = _run_risk(
        monkeypatch,
        reason=reason,
    )

    context = result["rendered"]["context"]

    assert [
        row["member_name"]
        for row in context["cleanup_members"]
    ] == cleanup_names

    assert [
        row["member_name"]
        for row in context["observe_members"]
    ] == observe_names

    assert context["selected_reason"] == reason

    assert not any(
        category == "warning"
        for _, category
        in result["flashes"]
    )


def test_invalid_reason_cannot_become_arbitrary_filter(
    monkeypatch,
):
    result = _run_risk(
        monkeypatch,
        reason="任意未授权条件",
    )

    context = result["rendered"]["context"]

    assert context["selected_reason"] == ""

    assert [
        row["member_name"]
        for row in context["cleanup_members"]
    ] == [
        "clear_member",
    ]

    assert [
        row["member_name"]
        for row in context["observe_members"]
    ] == [
        "danger_member",
        "warning_member",
    ]

    assert any(
        category == "warning"
        and "无效的风险原因筛选条件" in message
        for message, category
        in result["flashes"]
    )


def test_valid_reason_domain_is_exactly_frozen():
    tree = ast.parse(
        _risk_source()
    )

    values = None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        if not any(
            isinstance(target, ast.Name)
            and target.id == "valid_reasons"
            for target in node.targets
        ):
            continue

        values = ast.literal_eval(
            node.value
        )
        break

    assert values == VALID_REASONS


def test_route_sql_is_battle_scoped_latest_and_non_deleted():
    source = _risk_source()

    assert (
        "SELECT id FROM battles "
        "WHERE id = ? LIMIT 1"
    ) in " ".join(
        source.split()
    )

    assert "SELECT MAX(snapshot_time)" in source
    assert "WHERE battle_id = ?" in source
    assert "snapshot_time = ?" in source

    assert source.count(
        "is_deleted = 0"
    ) >= 2


def test_missing_resolved_battle_does_not_fallback(
    monkeypatch,
):
    result = _run_risk(
        monkeypatch,
        battle_exists=False,
    )

    context = result["rendered"]["context"]

    assert context["high_risk"] == []
    assert context["warning_risk"] == []
    assert context["protected"] == []

    assert context["cleanup_members"] == []
    assert context["observe_members"] == []
    assert context["protected_members"] == []

    assert context["risk_rate"] == 0.0

    player_queries = [
        sql
        for sql, _ in result["conn"].calls
        if "FROM player_records" in sql
    ]

    assert player_queries == []


def test_template_hash_and_render_context_contract():
    template_path = (
        __import__("pathlib")
        .Path(__file__)
        .resolve()
        .parents[1]
        / "templates"
        / "risk_center.html"
    )

    content = template_path.read_bytes()

    assert hashlib.sha256(
        content
    ).hexdigest() == EXPECTED_TEMPLATE_SHA256

    source = content.decode("utf-8")

    env = Environment()
    tree = env.parse(source)

    variables = set(
        meta.find_undeclared_variables(tree)
    )

    framework_vars = {
        "url_for",
        "request",
        "session",
        "config",
        "g",
        "get_flashed_messages",
    }

    variables -= framework_vars

    assert variables == {
        "cleanup_members",
        "high_risk",
        "observe_members",
        "protected",
        "protected_members",
        "risk_members_by_reason",
        "risk_rate",
        "risk_stats",
        "warning_risk",
    }


def test_required_contract_registry_is_complete():
    assert len(REQUIRED_CONTRACT_IDS) == 12

    assert set(
        REQUIRED_CONTRACT_IDS
    ) == {
        "AUTH_PROTECTED",
        "WORKSPACE_BOUNDARY",
        "LATEST_NON_DELETED_SNAPSHOT",
        "CLEAR_TO_CLEANUP",
        "DANGER_WARNING_TO_OBSERVE",
        "PROTECTED_TO_PROTECTED",
        "RISK_RATE",
        "FOUR_REASON_FILTERS",
        "INVALID_REASON_SAFE",
        "TEMPLATE_CONTEXT",
        "NO_CROSS_BATTLE_LEAK",
        "TEMPLATE_HASH_UNCHANGED",
    }
