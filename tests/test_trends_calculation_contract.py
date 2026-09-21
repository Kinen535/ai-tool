from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
TEMPLATE_PATH = ROOT / "templates" / "trends.html"

APP_SOURCE = APP_PATH.read_text(
    encoding="utf-8",
)

TEMPLATE_SOURCE = TEMPLATE_PATH.read_text(
    encoding="utf-8",
)

APP_TREE = ast.parse(
    APP_SOURCE,
    filename=str(APP_PATH),
)


def find_route_function(
    route_path: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    matches = []

    for node in APP_TREE.body:
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
                and decorator.func.attr == "route"
            ):
                continue

            if not decorator.args:
                continue

            argument = decorator.args[0]

            if (
                isinstance(
                    argument,
                    ast.Constant,
                )
                and argument.value == route_path
            ):
                matches.append(node)

    assert len(matches) == 1, (
        f"{route_path}路由数量异常："
        f"{len(matches)}"
    )

    return matches[0]


TRENDS_NODE = find_route_function(
    "/trends"
)

TRENDS_SOURCE = (
    ast.get_source_segment(
        APP_SOURCE,
        TRENDS_NODE,
    )
    or ""
)


def trends_sql_literals() -> list[str]:
    result = []

    for node in ast.walk(
        TRENDS_NODE
    ):
        if not (
            isinstance(
                node,
                ast.Constant,
            )
            and isinstance(
                node.value,
                str,
            )
        ):
            continue

        if re.search(
            r"\b(?:SELECT|FROM|WHERE|ORDER\s+BY)\b",
            node.value,
            flags=re.IGNORECASE,
        ):
            result.append(
                node.value
            )

    return result


SQL_LITERALS = trends_sql_literals()


def test_power_field_contract_keeps_populated_power_value() -> None:
    """power_total当前未填充，趋势计算必须继续读取power_value。"""

    player_queries = [
        sql
        for sql in SQL_LITERALS
        if re.search(
            r"\bFROM\s+player_records\b",
            sql,
            flags=re.IGNORECASE,
        )
    ]

    assert player_queries

    history_queries = [
        sql
        for sql in player_queries
        if re.search(
            r"\bbattle_total\b",
            sql,
            flags=re.IGNORECASE,
        )
        and re.search(
            r"\bassist_total\b",
            sql,
            flags=re.IGNORECASE,
        )
    ]

    assert history_queries

    assert any(
        re.search(
            r"\bpower_value\b",
            sql,
            flags=re.IGNORECASE,
        )
        for sql in history_queries
    )

    assert not any(
        re.search(
            r"\bpower_total\b",
            sql,
            flags=re.IGNORECASE,
        )
        for sql in history_queries
    )

    assert re.search(
        r"power_raw\s*=\s*"
        r"row\.get\s*\(\s*"
        r"[\"']power_value[\"']",
        TRENDS_SOURCE,
    )


def test_signed_deltas_are_not_silently_clamped_to_zero() -> None:
    """真实下降必须保留负数，不能通过max(0, delta)改写为0。"""

    clamped_metrics = []

    for metric in (
        "battle",
        "assist",
        "power",
    ):
        if re.search(
            rf"\b{metric}_growth\s*=\s*"
            rf"max\s*\(\s*0\s*,",
            TRENDS_SOURCE,
            flags=re.DOTALL,
        ):
            clamped_metrics.append(
                metric
            )

    assert not clamped_metrics, (
        "以下增量仍被静默归零："
        + ", ".join(
            clamped_metrics
        )
    )


def test_session_reset_does_not_use_the_legacy_35_percent_heuristic() -> None:
    """不得用任一累计指标跌至35%以下作为整段会话断层依据。"""

    assert not re.search(
        r"\*\s*0\.35\b",
        TRENDS_SOURCE,
    ), (
        "仍检测到35%累计值断层启发式。"
    )


def test_missing_current_battle_never_falls_back_to_battle_one() -> None:
    """没有当前战场时必须返回空结果，不能静默读取battle_id=1。"""

    fallback_assignments = []

    for node in ast.walk(
        TRENDS_NODE
    ):
        if not isinstance(
            node,
            ast.Assign,
        ):
            continue

        if not any(
            isinstance(
                target,
                ast.Name,
            )
            and target.id == "battle_id"
            for target in node.targets
        ):
            continue

        if not isinstance(
            node.value,
            ast.IfExp,
        ):
            continue

        if (
            isinstance(
                node.value.orelse,
                ast.Constant,
            )
            and node.value.orelse.value == 1
        ):
            fallback_assignments.append(
                node.lineno
            )

    assert not fallback_assignments, (
        "battle_id仍在以下行静默回退到1："
        f"{fallback_assignments}"
    )


def test_member_candidates_are_scoped_to_current_latest_roster() -> None:
    """搜索候选来自当前战场最新有效名单，历史查询仍可读取选中成员全历史。"""

    candidate_queries = [
        sql
        for sql in SQL_LITERALS
        if re.search(
            r"\bSELECT\s+DISTINCT\s+member\b",
            sql,
            flags=(
                re.IGNORECASE
                | re.DOTALL
            ),
        )
    ]

    assert candidate_queries, (
        "未定位到成员候选查询。"
    )

    assert any(
        re.search(
            r"\bMAX\s*\(\s*snapshot_time\s*\)",
            sql,
            flags=(
                re.IGNORECASE
                | re.DOTALL
            ),
        )
        and re.search(
            r"\bsnapshot_time\b",
            sql,
            flags=re.IGNORECASE,
        )
        and re.search(
            r"\bis_deleted\s*=\s*0\b",
            sql,
            flags=re.IGNORECASE,
        )
        for sql in candidate_queries
    ), (
        "成员候选查询尚未限定到当前战场最新有效快照。"
    )


def test_apexcharts_uses_real_datetime_x_axis() -> None:
    """采样间隔不等时必须按真实时间定位，不能使用等距categories。"""

    assert re.search(
        r"\bxaxis\s*:\s*\{"
        r".{0,1200}?"
        r"\btype\s*:\s*"
        r"[\"']datetime[\"']",
        TEMPLATE_SOURCE,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    ), (
        "ApexCharts尚未配置datetime横轴。"
    )

    assert not re.search(
        r"\bcategories\s*:",
        TEMPLATE_SOURCE,
        flags=re.IGNORECASE,
    ), (
        "模板仍使用等距categories横轴。"
    )

    assert re.search(
        r"\bx\s*:\s*"
        r"(?:Date\.parse\s*\(|"
        r"new\s+Date\s*\(|"
        r"[A-Za-z_][A-Za-z0-9_]*"
        r"\.(?:full_time|snapshot_time))",
        TEMPLATE_SOURCE,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    ), (
        "图表序列尚未输出真实时间x值。"
    )


# === V15.5-A7-A8 GROUP TRENDS CONTRACT TESTS ===


def _extract_app_function(
    function_name: str,
):
    matches = [
        node
        for node in APP_TREE.body
        if (
            isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
            and node.name == function_name
        )
    ]

    assert len(matches) == 1, (
        f"未找到唯一函数 {function_name}，"
        f"实际数量={len(matches)}"
    )

    module = ast.Module(
        body=[matches[0]],
        type_ignores=[],
    )

    ast.fix_missing_locations(
        module
    )

    namespace: dict[str, object] = {}

    exec(
        compile(
            module,
            filename=str(APP_PATH),
            mode="exec",
        ),
        namespace,
    )

    return namespace[
        function_name
    ]


def _group_row(
    row_id: int,
    snapshot_time: str,
    member: str,
    group_name: str,
    *,
    battle_total: int = 0,
    assist_total: int = 0,
    donate_total: int = 0,
    power_value: int = 0,
) -> dict:
    return {
        "id": row_id,
        "snapshot_time": snapshot_time,
        "member": member,
        "group_name": group_name,
        "battle_total": battle_total,
        "assist_total": assist_total,
        "donate_total": donate_total,
        "power_value": power_value,
    }


def _build_group_rows(
    records: list[dict],
    group_name: str,
) -> list[dict]:
    builder = _extract_app_function(
        "build_group_trend_rows"
    )

    result = builder(
        records,
        group_name,
        min_paired_members=5,
        min_baseline_coverage=0.90,
    )

    assert isinstance(
        result,
        list,
    )

    return result


def test_group_interval_uses_t1_historical_membership() -> None:
    records = []

    for index in range(5):
        member = f"成员{index}"

        records.append(
            _group_row(
                index + 1,
                "2026-01-01 00:00:00",
                member,
                "旧组",
                battle_total=100,
                assist_total=10,
                donate_total=1000,
                power_value=10000,
            )
        )

        records.append(
            _group_row(
                index + 101,
                "2026-01-02 00:00:00",
                member,
                "新组",
                battle_total=110,
                assist_total=12,
                donate_total=1100,
                power_value=9990,
            )
        )

    rows = _build_group_rows(
        records,
        "新组",
    )

    assert len(rows) == 1

    row = rows[0]

    assert row["group_name"] == "新组"
    assert row["paired_members"] == 5
    assert row["battle_delta_total"] == 50
    assert row["assist_delta_total"] == 10
    assert row["donate_delta_total"] == 500
    assert row["power_delta_total"] == -50


def test_group_member_move_keeps_each_interval_with_its_t1_group() -> None:
    records = []

    for index in range(5):
        member = f"成员{index}"

        records.extend(
            [
                _group_row(
                    index + 1,
                    "2026-01-01 00:00:00",
                    member,
                    "甲组",
                    battle_total=100,
                ),
                _group_row(
                    index + 101,
                    "2026-01-02 00:00:00",
                    member,
                    "甲组",
                    battle_total=110,
                ),
                _group_row(
                    index + 201,
                    "2026-01-03 00:00:00",
                    member,
                    "乙组",
                    battle_total=130,
                ),
            ]
        )

    group_a = _build_group_rows(
        records,
        "甲组",
    )

    group_b = _build_group_rows(
        records,
        "乙组",
    )

    assert len(group_a) == 1
    assert len(group_b) == 1

    assert (
        group_a[0][
            "snapshot_time"
        ]
        == "2026-01-02 00:00:00"
    )

    assert (
        group_b[0][
            "snapshot_time"
        ]
        == "2026-01-03 00:00:00"
    )

    assert (
        group_a[0][
            "battle_delta_total"
        ]
        == 50
    )

    assert (
        group_b[0][
            "battle_delta_total"
        ]
        == 100
    )


def test_group_signed_negative_delta_is_preserved() -> None:
    records = []

    for index in range(5):
        member = f"成员{index}"

        records.extend(
            [
                _group_row(
                    index + 1,
                    "2026-01-01 00:00:00",
                    member,
                    "甲组",
                    power_value=100,
                ),
                _group_row(
                    index + 101,
                    "2026-01-02 00:00:00",
                    member,
                    "甲组",
                    power_value=90,
                ),
            ]
        )

    row = _build_group_rows(
        records,
        "甲组",
    )[0]

    assert row["power_delta_total"] == -50
    assert row["power_delta_avg"] == -10


def test_group_new_member_without_t0_is_missing_baseline() -> None:
    records = []

    for index in range(5):
        member = f"成员{index}"

        records.extend(
            [
                _group_row(
                    index + 1,
                    "2026-01-01 00:00:00",
                    member,
                    "甲组",
                    battle_total=100,
                ),
                _group_row(
                    index + 101,
                    "2026-01-02 00:00:00",
                    member,
                    "甲组",
                    battle_total=110,
                ),
            ]
        )

    records.append(
        _group_row(
            999,
            "2026-01-02 00:00:00",
            "新成员",
            "甲组",
            battle_total=5000,
        )
    )

    row = _build_group_rows(
        records,
        "甲组",
    )[0]

    assert row["candidate_members"] == 6
    assert row["paired_members"] == 5
    assert row["missing_baseline_members"] == 1

    assert row["battle_delta_total"] == 50


def test_group_coverage_is_paired_over_candidates() -> None:
    records = []

    for index in range(5):
        member = f"成员{index}"

        records.extend(
            [
                _group_row(
                    index + 1,
                    "2026-01-01 00:00:00",
                    member,
                    "甲组",
                ),
                _group_row(
                    index + 101,
                    "2026-01-02 00:00:00",
                    member,
                    "甲组",
                ),
            ]
        )

    records.append(
        _group_row(
            999,
            "2026-01-02 00:00:00",
            "无基线成员",
            "甲组",
        )
    )

    row = _build_group_rows(
        records,
        "甲组",
    )[0]

    assert row["coverage"] == pytest.approx(
        5 / 6
    )


def test_group_interval_invalid_when_paired_members_below_five() -> None:
    records = []

    for index in range(4):
        member = f"成员{index}"

        records.extend(
            [
                _group_row(
                    index + 1,
                    "2026-01-01 00:00:00",
                    member,
                    "甲组",
                ),
                _group_row(
                    index + 101,
                    "2026-01-02 00:00:00",
                    member,
                    "甲组",
                ),
            ]
        )

    row = _build_group_rows(
        records,
        "甲组",
    )[0]

    assert row["paired_members"] == 4
    assert row["coverage"] == pytest.approx(
        1.0
    )
    assert row["is_valid"] is False


def test_group_interval_invalid_when_coverage_below_point_nine() -> None:
    records = []

    for index in range(8):
        member = f"成员{index}"

        records.extend(
            [
                _group_row(
                    index + 1,
                    "2026-01-01 00:00:00",
                    member,
                    "甲组",
                ),
                _group_row(
                    index + 101,
                    "2026-01-02 00:00:00",
                    member,
                    "甲组",
                ),
            ]
        )

    for index in range(2):
        records.append(
            _group_row(
                900 + index,
                "2026-01-02 00:00:00",
                f"新成员{index}",
                "甲组",
            )
        )

    row = _build_group_rows(
        records,
        "甲组",
    )[0]

    assert row["paired_members"] == 8
    assert row["candidate_members"] == 10
    assert row["coverage"] == pytest.approx(
        0.8
    )
    assert row["is_valid"] is False


def test_group_valid_interval_has_totals_and_per_member_averages() -> None:
    records = []

    for index in range(5):
        member = f"成员{index}"

        records.extend(
            [
                _group_row(
                    index + 1,
                    "2026-01-01 00:00:00",
                    member,
                    "甲组",
                    battle_total=100,
                    assist_total=10,
                    donate_total=1000,
                    power_value=100,
                ),
                _group_row(
                    index + 101,
                    "2026-01-02 00:00:00",
                    member,
                    "甲组",
                    battle_total=110,
                    assist_total=12,
                    donate_total=1100,
                    power_value=99,
                ),
            ]
        )

    row = _build_group_rows(
        records,
        "甲组",
    )[0]

    assert row["is_valid"] is True

    assert row["battle_delta_total"] == 50
    assert row["assist_delta_total"] == 10
    assert row["donate_delta_total"] == 500
    assert row["power_delta_total"] == -5

    assert row["battle_delta_avg"] == 10
    assert row["assist_delta_avg"] == 2
    assert row["donate_delta_avg"] == 100
    assert row["power_delta_avg"] == -1


def test_group_options_include_historical_groups_absent_from_latest() -> None:
    builder = _extract_app_function(
        "build_group_options"
    )

    records = [
        _group_row(
            1,
            "2026-01-01 00:00:00",
            "成员A",
            "历史旧组",
        ),
        _group_row(
            2,
            "2026-01-02 00:00:00",
            "成员A",
            "当前新组",
        ),
    ]

    result = builder(
        records
    )

    assert set(result) == {
        "历史旧组",
        "当前新组",
    }


def test_group_mode_route_and_template_contract() -> None:
    assert re.search(
        r"request\.args\.get\s*\(\s*"
        r"[\"']mode[\"']",
        TRENDS_SOURCE,
    )

    assert "group_options" in TRENDS_SOURCE
    assert "group_trend_rows" in TRENDS_SOURCE

    assert re.search(
        r'name\s*=\s*["\']mode["\']',
        TEMPLATE_SOURCE,
    )

    assert re.search(
        r'value\s*=\s*["\']group["\']',
        TEMPLATE_SOURCE,
    )

    assert "group_options" in TEMPLATE_SOURCE
    assert "group_trend_rows" in TEMPLATE_SOURCE

    assert (
        "后续版本接入团级聚合分析"
        not in TEMPLATE_SOURCE
    )
