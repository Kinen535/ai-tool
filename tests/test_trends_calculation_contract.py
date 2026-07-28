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
