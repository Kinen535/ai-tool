from __future__ import annotations

import hashlib
import inspect
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import g
from jinja2 import Environment, meta

import app as app_module


EXPECTED_TEMPLATE_SHA256 = (
    "085ede4f9b8f3821410bb299419f8f9f3167fa99a2089bd50a688ee954c4ab5a"
)

EXPECTED_CONTEXT_KEYS = {
    "clean_count",
    "clean_members",
    "member_count",
    "summary",
    "train_count",
    "train_members",
    "watch_count",
    "watch_members",
}

REQUIRED_CONTRACT_IDS = (
    "AUTH_PROTECTED",
    "WORKSPACE_BOUNDARY",
    "LATEST_NON_DELETED_SAME_BATTLE_SNAPSHOT",
    "NO_CROSS_BATTLE_LEAK",
    "TRAIN_RULE",
    "WATCH_RULE",
    "CLEAN_RULE",
    "PROTECTED_EXCLUSION",
    "LEADER_ADMIN_CLEAN_EXCLUSION",
    "TOP3_SELECTION",
    "TEMPLATE_CONTEXT",
    "TEMPLATE_HASH_UNCHANGED",
    "CONTRACT_REGISTRY",
)


def _ai_daily_view():
    return inspect.unwrap(app_module.ai_daily)


def _ai_daily_source():
    return textwrap.dedent(
        inspect.getsource(_ai_daily_view())
    )


def _member(
    name,
    *,
    av=0,
    bs=0,
    identity_score=0,
    risk_level="safe",
    risk_reason="",
    role_tag="member",
    is_protected=0,
    trend="stable",
    exempt_stall=0,
):
    return {
        "member_name": name,
        "av": av,
        "bs": bs,
        "trend": trend,
        "risk_level": risk_level,
        "risk_reason": risk_reason,
        "role_tag": role_tag,
        "identity_score": identity_score,
        "is_protected": is_protected,
        "exempt_stall": exempt_stall,
    }


def _default_rows():
    return [
        _member(
            "train_member",
            av=80,
            bs=80,
            identity_score=90,
            risk_level="safe",
        ),
        _member(
            "watch_member",
            av=30,
            bs=30,
            identity_score=20,
            risk_level="danger",
            risk_reason="活跃不足｜连续停滞",
        ),
        _member(
            "clean_member",
            av=10,
            bs=20,
            identity_score=10,
            risk_level="clear",
            risk_reason="长期低贡献",
        ),
        _member(
            "protected_warning",
            av=20,
            bs=20,
            identity_score=10,
            risk_level="warning",
            risk_reason="综合健康分过低",
            is_protected=1,
        ),
        _member(
            "leader_clear",
            av=10,
            bs=10,
            identity_score=5,
            risk_level="clear",
            role_tag="leader",
        ),
        _member(
            "admin_clear",
            av=10,
            bs=10,
            identity_score=5,
            risk_level="clear",
            role_tag="admin",
        ),
    ]


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, rows=None):
        self.rows = list(
            _default_rows()
            if rows is None
            else rows
        )
        self.row_factory = None
        self.calls = []
        self.closed = False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        params = tuple(params)

        self.calls.append((normalized, params))

        assert "FROM player_records AS pr" in normalized
        assert "WHERE pr.battle_id = ?" in normalized
        assert "pr.is_deleted = 0" in normalized
        assert "SELECT MAX(p2.snapshot_time)" in normalized
        assert "WHERE p2.battle_id = pr.battle_id" in normalized
        assert "p2.is_deleted = 0" in normalized
        assert "COALESCE(p2.snapshot_time, '')" in normalized
        assert params == (6,)

        return _Result(self.rows)

    def close(self):
        self.closed = True


def _run_ai_daily(monkeypatch, *, rows=None):
    conn = _FakeConn(rows=rows)

    rendered = {}
    resolver_seen = {}
    connect_seen = {}

    access_context = object()

    def fake_resolver(value):
        resolver_seen["value"] = value
        return SimpleNamespace(
            current_battle_id=6
        )

    def fake_connect(path):
        connect_seen["path"] = path
        assert path == app_module.DB_PATH
        return conn

    def fake_render(template_name, **context):
        rendered["template"] = template_name
        rendered["context"] = context
        return "AI_DAILY_RENDERED"

    monkeypatch.setattr(
        app_module,
        "resolve_workspace_data_boundary",
        fake_resolver,
    )

    monkeypatch.setattr(
        app_module.sqlite3,
        "connect",
        fake_connect,
    )

    monkeypatch.setattr(
        app_module,
        "render_template",
        fake_render,
    )

    with app_module.app.test_request_context(
        "/ai/daily"
    ):
        g.v155_access_context = access_context
        response = _ai_daily_view()()

    return {
        "response": response,
        "conn": conn,
        "rendered": rendered,
        "resolver_seen": resolver_seen,
        "connect_seen": connect_seen,
        "access_context": access_context,
    }


def test_ai_daily_remains_authentication_protected():
    client = app_module.app.test_client()

    response = client.get(
        "/ai/daily",
        follow_redirects=False,
    )

    assert response.status_code == 302


def test_workspace_boundary_and_sql_contract(monkeypatch):
    result = _run_ai_daily(monkeypatch)

    assert (
        result["resolver_seen"]["value"]
        is result["access_context"]
    )

    assert result["connect_seen"]["path"] == app_module.DB_PATH
    assert result["conn"].row_factory is app_module.sqlite3.Row
    assert result["conn"].closed is True

    assert len(result["conn"].calls) == 1

    sql, params = result["conn"].calls[0]

    assert params == (6,)
    assert "FROM player_records AS pr" in sql
    assert "WHERE pr.battle_id = ?" in sql
    assert "pr.is_deleted = 0" in sql
    assert "SELECT MAX(p2.snapshot_time)" in sql
    assert "WHERE p2.battle_id = pr.battle_id" in sql
    assert "p2.is_deleted = 0" in sql
    assert "COALESCE(p2.snapshot_time, '')" in sql

    assert result["rendered"]["template"] == "ai_daily.html"


def test_train_rule_is_exact(monkeypatch):
    rows = [
        _member(
            "score64",
            av=90,
            bs=90,
            identity_score=64,
        ),
        _member(
            "av49",
            av=49,
            bs=90,
            identity_score=90,
        ),
        _member(
            "bs59",
            av=90,
            bs=59,
            identity_score=90,
        ),
        _member(
            "exact_threshold",
            av=50,
            bs=60,
            identity_score=65,
        ),
    ]

    result = _run_ai_daily(
        monkeypatch,
        rows=rows,
    )

    context = result["rendered"]["context"]

    assert context["train_count"] == 1
    assert [
        row["member_name"]
        for row in context["train_members"]
    ] == ["exact_threshold"]


def test_watch_rule_and_protected_exclusion(monkeypatch):
    rows = [
        _member(
            "danger",
            risk_level="danger",
        ),
        _member(
            "warning",
            risk_level="warning",
        ),
        _member(
            "protected_danger",
            risk_level="danger",
            is_protected=1,
        ),
        _member(
            "safe",
            risk_level="safe",
        ),
    ]

    result = _run_ai_daily(
        monkeypatch,
        rows=rows,
    )

    context = result["rendered"]["context"]

    assert context["watch_count"] == 2

    names = {
        row["member_name"]
        for row in context["watch_members"]
    }

    assert names == {
        "danger",
        "warning",
    }


def test_clean_rule_protection_and_role_exclusion(monkeypatch):
    rows = [
        _member(
            "clean_member",
            risk_level="clear",
        ),
        _member(
            "protected_clean",
            risk_level="clear",
            is_protected=1,
        ),
        _member(
            "leader_clean",
            risk_level="clear",
            role_tag="leader",
        ),
        _member(
            "admin_clean",
            risk_level="clear",
            role_tag="admin",
        ),
        _member(
            "warning_member",
            risk_level="warning",
        ),
    ]

    result = _run_ai_daily(
        monkeypatch,
        rows=rows,
    )

    context = result["rendered"]["context"]

    assert context["clean_count"] == 1
    assert [
        row["member_name"]
        for row in context["clean_members"]
    ] == ["clean_member"]


def test_top3_summary_and_render_limit_10(monkeypatch):
    train_rows = [
        _member(
            f"train_{i:02d}",
            av=70 + i,
            bs=70 + i,
            identity_score=70 + i,
            risk_level="safe",
        )
        for i in range(12)
    ]

    clean_rows = [
        _member(
            f"clean_{i:02d}",
            av=i,
            bs=i,
            identity_score=0,
            risk_level="clear",
            risk_reason=f"reason_{i:02d}",
        )
        for i in range(12)
    ]

    result = _run_ai_daily(
        monkeypatch,
        rows=train_rows + clean_rows,
    )

    context = result["rendered"]["context"]
    summary = context["summary"]

    assert context["train_count"] == 12
    assert context["clean_count"] == 12

    assert len(context["train_members"]) == 10
    assert len(context["clean_members"]) == 10

    assert "train_11、train_10、train_09" in summary

    assert "clean_00（reason_00）" in summary
    assert "clean_01（reason_01）" in summary
    assert "clean_02（reason_02）" in summary
    assert "clean_03（reason_03）" not in summary


def test_no_cross_battle_fallback_is_present_in_route_source():
    source = _ai_daily_source()

    assert "resolve_workspace_data_boundary" in source
    assert "battle_id = int(_v155_boundary.current_battle_id)" in source

    assert "WHERE pr.battle_id = ?" in source
    assert "WHERE p2.battle_id = pr.battle_id" in source

    assert "sqlite3.connect(DB_PATH)" in source
    assert "get_conn(" not in source


def test_template_hash_and_exact_context_contract():
    template_path = (
        Path(app_module.__file__).resolve().parent
        / "templates"
        / "ai_daily.html"
    )

    content = template_path.read_bytes()

    assert (
        hashlib.sha256(content).hexdigest()
        == EXPECTED_TEMPLATE_SHA256
    )

    env = Environment()
    parsed = env.parse(
        content.decode("utf-8")
    )

    variables = set(
        meta.find_undeclared_variables(parsed)
    )

    assert variables == EXPECTED_CONTEXT_KEYS


def test_required_contract_registry_is_complete():
    assert REQUIRED_CONTRACT_IDS == (
        "AUTH_PROTECTED",
        "WORKSPACE_BOUNDARY",
        "LATEST_NON_DELETED_SAME_BATTLE_SNAPSHOT",
        "NO_CROSS_BATTLE_LEAK",
        "TRAIN_RULE",
        "WATCH_RULE",
        "CLEAN_RULE",
        "PROTECTED_EXCLUSION",
        "LEADER_ADMIN_CLEAN_EXCLUSION",
        "TOP3_SELECTION",
        "TEMPLATE_CONTEXT",
        "TEMPLATE_HASH_UNCHANGED",
        "CONTRACT_REGISTRY",
    )
