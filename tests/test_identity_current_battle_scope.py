from __future__ import annotations

import ast
import copy
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable

import pytest
from flask import Flask, request


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
CURRENT_BATTLE_ID = 2
OTHER_BATTLE_ID = 1

OLD_SNAPSHOT = "2026-01-01 08:00:00"
LATEST_SNAPSHOT = "2026-01-02 08:00:00"
OTHER_SNAPSHOT = "2026-01-03 08:00:00"

LATEST_MEMBERS = {
    "当前丨甲",
    "当前丨乙",
    "当前丨丙",
}

GLOBAL_ONLY_MEMBERS = {
    "全局旧档案甲",
    "全局旧档案乙",
    "全局旧档案丙",
    "全局旧档案丁",
    "全局旧档案戊",
}

STALE_CURRENT_MEMBER = "当前战场历史成员"
OTHER_BATTLE_MEMBER = "其他战场成员"
DELETED_LATEST_MEMBER = "当前战场已删除成员"


def _identity_function_node() -> tuple[
    str,
    ast.FunctionDef | ast.AsyncFunctionDef,
]:
    source = APP_PATH.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        source,
        filename=str(APP_PATH),
    )

    matches: list[
        ast.FunctionDef | ast.AsyncFunctionDef
    ] = []

    for node in tree.body:
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        for decorator in node.decorator_list:
            if not isinstance(
                decorator,
                ast.Call,
            ):
                continue

            if not (
                isinstance(
                    decorator.func,
                    ast.Attribute,
                )
                and decorator.func.attr
                == "route"
            ):
                continue

            if not decorator.args:
                continue

            route_argument = (
                decorator.args[0]
            )

            if (
                isinstance(
                    route_argument,
                    ast.Constant,
                )
                and route_argument.value
                == "/identity"
            ):
                matches.append(node)
                break

    if len(matches) != 1:
        raise AssertionError(
            "正式app.py中的/identity"
            "主路由数量异常："
            f"{len(matches)}"
        )

    return source, matches[0]


def _build_identity_runner(
    database_path: Path,
) -> Callable[[str], dict[str, Any]]:
    source, original_node = (
        _identity_function_node()
    )

    identity_node = copy.deepcopy(
        original_node
    )
    identity_node.decorator_list = []

    module = ast.Module(
        body=[identity_node],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)

    rendered_calls: list[
        dict[str, Any]
    ] = []

    def get_conn() -> sqlite3.Connection:
        connection = sqlite3.connect(
            (
                f"file:{database_path}"
                "?mode=ro"
            ),
            uri=True,
        )
        connection.row_factory = (
            sqlite3.Row
        )
        connection.execute(
            "PRAGMA query_only = ON"
        )

        query_only = connection.execute(
            "PRAGMA query_only"
        ).fetchone()[0]

        if query_only != 1:
            connection.close()
            raise AssertionError(
                "测试连接没有启用"
                "SQLite query_only。"
            )

        return connection

    def capture_render_template(
        template_name: str,
        **context: Any,
    ) -> dict[str, Any]:
        captured = {
            "template_name": template_name,
            "context": context,
        }
        rendered_calls.append(captured)
        return captured

    namespace: dict[str, Any] = {
        "__builtins__": __builtins__,
        "get_conn": get_conn,
        "request": request,
        "render_template": (
            capture_render_template
        ),
    }

    exec(
        compile(
            module,
            filename=str(APP_PATH),
            mode="exec",
        ),
        namespace,
    )

    identity_function = namespace.get(
        original_node.name
    )

    if not callable(identity_function):
        raise AssertionError(
            "AST隔离执行没有生成"
            "identity函数。"
        )

    flask_app = Flask(
        "identity-current-battle-"
        "scope-tests"
    )

    def run(
        query_string: str = "",
    ) -> dict[str, Any]:
        before_count = len(
            rendered_calls
        )

        request_path = "/identity"

        if query_string:
            request_path += (
                "?"
                + query_string
            )

        with (
            flask_app
            .test_request_context(
                request_path
            )
        ):
            result = identity_function()

        if len(rendered_calls) != (
            before_count + 1
        ):
            raise AssertionError(
                "identity函数没有产生"
                "唯一模板调用。"
            )

        captured = rendered_calls[-1]

        if result is not captured:
            raise AssertionError(
                "identity函数返回值与"
                "捕获模板结果不一致。"
            )

        if (
            captured["template_name"]
            != "identity.html"
        ):
            raise AssertionError(
                "identity函数没有渲染"
                "identity.html。"
            )

        return dict(
            captured["context"]
        )

    return run


def _create_test_database(
    database_path: Path,
) -> None:
    connection = sqlite3.connect(
        database_path
    )

    try:
        connection.executescript(
            """
            CREATE TABLE battles (
                id INTEGER PRIMARY KEY,
                battle_name TEXT,
                is_current INTEGER
                    NOT NULL DEFAULT 0
            );

            CREATE TABLE member_profiles (
                id INTEGER PRIMARY KEY
                    AUTOINCREMENT,
                member_name TEXT
            );

            CREATE TABLE
                member_battle_profiles (
                    id INTEGER PRIMARY KEY
                        AUTOINCREMENT,
                    battle_id INTEGER
                        NOT NULL,
                    member_name TEXT
                        NOT NULL,
                    role_tag TEXT,
                    role_desc TEXT,
                    role_rule TEXT,
                    role_weight REAL,
                    is_protected INTEGER,
                    exempt_stall INTEGER
                );

            CREATE TABLE player_records (
                id INTEGER PRIMARY KEY
                    AUTOINCREMENT,
                battle_id INTEGER
                    NOT NULL,
                snapshot_time TEXT,
                is_deleted INTEGER
                    NOT NULL DEFAULT 0,
                member TEXT,
                role_tag TEXT,
                role_desc TEXT,
                role_rule TEXT,
                role_weight REAL,
                identity_score REAL,
                is_protected INTEGER,
                exempt_stall INTEGER,
                av REAL,
                bs REAL,
                wv REAL,
                bv REAL,
                trend TEXT,
                risk_level TEXT,
                risk_reason TEXT,
                battle_gain REAL,
                assist_gain REAL,
                donate_gain REAL,
                group_name TEXT
            );
            """
        )

        connection.executemany(
            """
            INSERT INTO battles (
                id,
                battle_name,
                is_current
            )
            VALUES (?, ?, ?)
            """,
            [
                (
                    OTHER_BATTLE_ID,
                    "其他战场",
                    0,
                ),
                (
                    CURRENT_BATTLE_ID,
                    "当前战场",
                    1,
                ),
            ],
        )

        connection.executemany(
            """
            INSERT INTO member_profiles (
                member_name
            )
            VALUES (?)
            """,
            [
                (name,)
                for name in sorted(
                    GLOBAL_ONLY_MEMBERS
                )
            ],
        )

        connection.executemany(
            """
            INSERT INTO
                member_battle_profiles (
                    battle_id,
                    member_name,
                    role_tag,
                    role_desc,
                    role_rule,
                    role_weight,
                    is_protected,
                    exempt_stall
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    CURRENT_BATTLE_ID,
                    "当前丨甲",
                    "admin",
                    "当前管理员",
                    "normal",
                    1.2,
                    1,
                    1,
                ),
                (
                    CURRENT_BATTLE_ID,
                    "当前丨乙",
                    "core",
                    "当前核心",
                    "normal",
                    1.1,
                    0,
                    0,
                ),
                (
                    CURRENT_BATTLE_ID,
                    "当前丨丙",
                    "member",
                    "当前成员",
                    "normal",
                    1.0,
                    0,
                    0,
                ),
                (
                    CURRENT_BATTLE_ID,
                    STALE_CURRENT_MEMBER,
                    "warehouse",
                    "离盟历史档案",
                    "normal",
                    1.0,
                    0,
                    0,
                ),
                (
                    OTHER_BATTLE_ID,
                    OTHER_BATTLE_MEMBER,
                    "admin",
                    "其他战场管理员",
                    "normal",
                    1.0,
                    1,
                    1,
                ),
            ],
        )

        player_rows = [
            (
                CURRENT_BATTLE_ID,
                OLD_SNAPSHOT,
                0,
                "当前丨甲",
                "member",
                "",
                "normal",
                1.0,
                75.0,
                0,
                0,
                60.0,
                60.0,
                50.0,
                40.0,
                "stable",
                "safe",
                "",
                1.0,
                1.0,
                1.0,
                "当前组",
            ),
            (
                CURRENT_BATTLE_ID,
                OLD_SNAPSHOT,
                0,
                STALE_CURRENT_MEMBER,
                "member",
                "",
                "normal",
                1.0,
                77.0,
                0,
                0,
                55.0,
                55.0,
                45.0,
                35.0,
                "stable",
                "safe",
                "",
                2.0,
                1.0,
                1.0,
                "历史组",
            ),
            (
                CURRENT_BATTLE_ID,
                LATEST_SNAPSHOT,
                0,
                "当前丨甲",
                "member",
                "",
                "normal",
                1.0,
                95.0,
                0,
                0,
                85.0,
                85.0,
                80.0,
                70.0,
                "up",
                "safe",
                "",
                20.0,
                5.0,
                3.0,
                "当前组",
            ),
            (
                CURRENT_BATTLE_ID,
                LATEST_SNAPSHOT,
                0,
                "当前丨乙",
                "member",
                "",
                "normal",
                1.0,
                65.0,
                0,
                0,
                60.0,
                65.0,
                55.0,
                45.0,
                "up",
                "warning",
                "需要观察",
                10.0,
                3.0,
                2.0,
                "当前组",
            ),
            (
                CURRENT_BATTLE_ID,
                LATEST_SNAPSHOT,
                0,
                "当前丨丙",
                "member",
                "",
                "normal",
                1.0,
                20.0,
                0,
                0,
                10.0,
                10.0,
                10.0,
                5.0,
                "dead",
                "danger",
                "长期停滞",
                0.0,
                0.0,
                0.0,
                "当前组",
            ),
            (
                CURRENT_BATTLE_ID,
                LATEST_SNAPSHOT,
                1,
                DELETED_LATEST_MEMBER,
                "admin",
                "",
                "normal",
                1.0,
                99.0,
                1,
                1,
                99.0,
                99.0,
                99.0,
                99.0,
                "explosive",
                "safe",
                "",
                99.0,
                99.0,
                99.0,
                "已删除组",
            ),
            (
                OTHER_BATTLE_ID,
                OTHER_SNAPSHOT,
                0,
                OTHER_BATTLE_MEMBER,
                "admin",
                "",
                "normal",
                1.0,
                88.0,
                1,
                1,
                88.0,
                88.0,
                88.0,
                88.0,
                "explosive",
                "safe",
                "",
                50.0,
                10.0,
                5.0,
                "其他组",
            ),
        ]

        connection.executemany(
            """
            INSERT INTO player_records (
                battle_id,
                snapshot_time,
                is_deleted,
                member,
                role_tag,
                role_desc,
                role_rule,
                role_weight,
                identity_score,
                is_protected,
                exempt_stall,
                av,
                bs,
                wv,
                bv,
                trend,
                risk_level,
                risk_reason,
                battle_gain,
                assist_gain,
                donate_gain,
                group_name
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            player_rows,
        )

        connection.commit()

    finally:
        connection.close()


@pytest.fixture()
def identity_runner(
    tmp_path: Path,
) -> Callable[[str], dict[str, Any]]:
    database_path = (
        tmp_path
        / "identity_scope.sqlite3"
    )

    production_database = (
        ROOT
        / "data"
        / "snapshots.db"
    )

    assert (
        database_path.resolve()
        != production_database.resolve()
    )

    _create_test_database(
        database_path
    )

    return _build_identity_runner(
        database_path
    )


def test_identity_uses_only_current_battle_latest_active_roster(
    identity_runner: Callable[
        [str],
        dict[str, Any],
    ],
) -> None:
    context = identity_runner("")

    members = list(
        context["members"]
    )

    member_names = {
        str(item["member_name"])
        for item in members
    }

    assert context["total_members"] == 3
    assert len(members) == 3
    assert member_names == LATEST_MEMBERS

    assert not (
        member_names
        & GLOBAL_ONLY_MEMBERS
    )

    assert (
        STALE_CURRENT_MEMBER
        not in member_names
    )

    assert (
        OTHER_BATTLE_MEMBER
        not in member_names
    )

    assert (
        DELETED_LATEST_MEMBER
        not in member_names
    )

    assert context["admin_count"] == 1
    assert context["core_count"] == 1
    assert context["warehouse_count"] == 0
    assert context["protected_count"] == 1
    assert context["exempt_count"] == 1

    grade_total = sum(
        int(context[key])
        for key in (
            "s_count",
            "a_count",
            "b_count",
            "c_count",
            "d_count",
        )
    )

    assert grade_total == 3

    dashboard_lists = (
        "top_identity",
        "risk_members",
        "grow_members",
        "growth_members",
        "focus_members",
    )

    for list_name in dashboard_lists:
        values = list(
            context[list_name]
        )

        assert len(values) <= 10

        names = {
            str(item["member_name"])
            for item in values
        }

        assert names <= LATEST_MEMBERS

    assert {
        str(item["member_name"])
        for item in context[
            "top_identity"
        ]
    } == LATEST_MEMBERS

    assert {
        str(item["member_name"])
        for item in context[
            "risk_members"
        ]
    } == {"当前丨丙"}

    assert {
        str(item["member_name"])
        for item in context[
            "grow_members"
        ]
    } == {"当前丨乙"}


def test_identity_filters_preserve_unfiltered_dashboard_totals(
    identity_runner: Callable[
        [str],
        dict[str, Any],
    ],
) -> None:
    default_context = identity_runner(
        ""
    )
    admin_context = identity_runner(
        "role=admin"
    )
    grade_s_context = identity_runner(
        "grade=S"
    )
    missing_context = identity_runner(
        "keyword=__NO_SUCH_MEMBER__"
    )

    assert (
        default_context["total_members"]
        == 3
    )

    assert (
        admin_context["total_members"]
        == 3
    )

    assert [
        item["member_name"]
        for item in admin_context[
            "members"
        ]
    ] == ["当前丨甲"]

    assert (
        admin_context["admin_count"]
        == 1
    )

    assert (
        grade_s_context[
            "total_members"
        ]
        == 3
    )

    assert [
        item["member_name"]
        for item in grade_s_context[
            "members"
        ]
    ] == ["当前丨甲"]

    assert (
        grade_s_context["s_count"]
        == 1
    )

    assert (
        missing_context["total_members"]
        == 3
    )

    assert (
        missing_context["members"]
        == []
    )


def test_identity_source_contract_does_not_use_global_profile_table() -> None:
    source, node = (
        _identity_function_node()
    )

    route_source = (
        ast.get_source_segment(
            source,
            node,
        )
        or ""
    )

    normalized = re.sub(
        r"\s+",
        " ",
        route_source,
    )

    assert (
        "WHERE is_current = 1"
        in normalized
    )

    assert (
        "SELECT MAX(snapshot_time)"
        in normalized
    )

    assert (
        "WHERE pr.battle_id = ?"
        in normalized
    )

    assert (
        "AND pr.snapshot_time = ?"
        in normalized
    )

    assert (
        "AND pr.is_deleted = 0"
        in normalized
    )

    assert (
        "member_battle_profiles"
        in normalized
    )

    assert (
        "mp.battle_id=pr.battle_id"
        in normalized
    )

    assert not re.search(
        r"\b(?:FROM|JOIN)\s+"
        r"member_profiles\b",
        normalized,
        flags=re.IGNORECASE,
    )

    assert (
        "total_members = "
        "len(all_members)"
        in normalized
    )

    assert (
        "top_identity = "
        "sorted(all_members"
        in normalized
    )


def test_identity_without_current_battle_returns_empty_dashboard(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path
        / "identity_no_current.sqlite3"
    )

    _create_test_database(
        database_path
    )

    connection = sqlite3.connect(
        database_path
    )

    try:
        connection.execute(
            """
            UPDATE battles
            SET is_current = 0
            """
        )
        connection.commit()

    finally:
        connection.close()

    identity_runner = (
        _build_identity_runner(
            database_path
        )
    )

    context = identity_runner("")

    assert context["total_members"] == 0
    assert context["members"] == []

    for count_name in (
        "admin_count",
        "warehouse_count",
        "core_count",
        "protected_count",
        "exempt_count",
        "s_count",
        "a_count",
        "b_count",
        "c_count",
        "d_count",
    ):
        assert context[count_name] == 0

    for list_name in (
        "top_identity",
        "risk_members",
        "grow_members",
        "growth_members",
        "focus_members",
    ):
        assert context[list_name] == []

    assert context["health_score"] == 0.0
    assert context["health_level"] == "危险"

    assert context["ai_advice"] == [
        "当前战场暂无可用成员数据"
    ]
