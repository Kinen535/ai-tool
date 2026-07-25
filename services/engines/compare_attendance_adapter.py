from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from services.engines.attendance_engine import (
    build_configurable_attendance_dashboard,
)


NOT_INCLUDED_STATUS = "不计入"

SNAPSHOT_ALIASES = {
    "成员": (
        "成员",
        "member",
        "member_name",
    ),
    "分组": (
        "分组",
        "group_name",
        "team_name",
    ),
    "战功总量": (
        "战功总量",
        "battle_total",
    ),
    "助攻总量": (
        "助攻总量",
        "assist_total",
    ),
    "捐献总量": (
        "捐献总量",
        "donate_total",
    ),
}

ATTENDANCE_MEMBER_FIELDS = (
    "分组",
    "战功增长",
    "助攻增长",
    "捐献增长",
    "战功考勤状态",
    "助攻考勤状态",
    "捐献考勤状态",
    "战功考核标准",
    "助攻考核标准",
    "捐献考核标准",
    "综合考勤状态",
    "考勤排序等级",
    "合格项数",
    "未达标项数",
    "异常项数",
    "无基线项数",
    "是否有基线",
    "是否免考核",
)


def _as_records(
    source: Any,
    *,
    source_label: str,
) -> list[dict[str, Any]]:
    if source is None:
        return []

    if isinstance(source, Mapping):
        raw_records = [source]

    elif hasattr(source, "to_dict"):
        try:
            raw_records = source.to_dict(
                orient="records"
            )
        except TypeError:
            raw_records = source.to_dict(
                "records"
            )

    else:
        try:
            raw_records = list(source)
        except TypeError as error:
            raise TypeError(
                f"{source_label}必须是记录列表或DataFrame"
            ) from error

    records: list[dict[str, Any]] = []

    for index, row in enumerate(raw_records):
        if not isinstance(row, Mapping):
            raise TypeError(
                f"{source_label}第{index + 1}行"
                "不是字典记录"
            )

        records.append(dict(row))

    return records


def _pick_value(
    row: Mapping[str, Any],
    aliases: Iterable[str],
    default: Any = None,
) -> Any:
    for key in aliases:
        if key in row:
            return row[key]

    return default


def _normalize_snapshot_rows(
    source: Any,
    *,
    source_label: str,
) -> list[dict[str, Any]]:
    records = _as_records(
        source,
        source_label=source_label,
    )

    result: list[dict[str, Any]] = []

    for index, row in enumerate(records):
        normalized = dict(row)

        member_name = str(
            _pick_value(
                row,
                SNAPSHOT_ALIASES["成员"],
                "",
            )
            or ""
        ).strip()

        if not member_name:
            raise ValueError(
                f"{source_label}第{index + 1}行"
                "缺少成员名"
            )

        group_name = str(
            _pick_value(
                row,
                SNAPSHOT_ALIASES["分组"],
                "未分组",
            )
            or "未分组"
        ).strip() or "未分组"

        normalized["成员"] = member_name
        normalized["分组"] = group_name

        for canonical_key in (
            "战功总量",
            "助攻总量",
            "捐献总量",
        ):
            normalized[canonical_key] = (
                _pick_value(
                    row,
                    SNAPSHOT_ALIASES[
                        canonical_key
                    ],
                    0,
                )
            )

        result.append(normalized)

    return result


def _member_name(
    row: Mapping[str, Any],
) -> str:
    return str(
        _pick_value(
            row,
            SNAPSHOT_ALIASES["成员"],
            "",
        )
        or ""
    ).strip()


def _json_safe(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            bool,
            int,
        ),
    ):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            return None

        return value

    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _json_safe(item)
            for item in value
        ]

    item_method = getattr(
        value,
        "item",
        None,
    )

    if callable(item_method):
        try:
            return _json_safe(
                item_method()
            )
        except (TypeError, ValueError):
            pass

    isoformat_method = getattr(
        value,
        "isoformat",
        None,
    )

    if callable(isoformat_method):
        try:
            return isoformat_method()
        except (TypeError, ValueError):
            pass

    return str(value)


def enrich_compare_rows(
    compare_rows: Any,
    attendance_dashboard: Mapping[str, Any],
) -> list[dict[str, Any]]:
    records = _as_records(
        compare_rows,
        source_label="对比明细",
    )

    attendance_members = (
        attendance_dashboard.get(
            "成员明细",
            [],
        )
        or []
    )

    attendance_index = {
        str(member.get("成员", "")).strip():
            member
        for member in attendance_members
        if str(
            member.get("成员", "")
        ).strip()
    }

    result: list[dict[str, Any]] = []

    for row in records:
        output = dict(row)
        member_name = _member_name(row)

        if not member_name:
            raise ValueError(
                "对比明细存在空成员名"
            )

        attendance = attendance_index.get(
            member_name
        )

        if attendance is None:
            output.update({
                "战功考勤状态":
                    NOT_INCLUDED_STATUS,
                "助攻考勤状态":
                    NOT_INCLUDED_STATUS,
                "捐献考勤状态":
                    NOT_INCLUDED_STATUS,
                "综合考勤状态":
                    NOT_INCLUDED_STATUS,
                "考勤排序等级": 999,
                "合格项数": 0,
                "未达标项数": 0,
                "异常项数": 0,
                "无基线项数": 0,
                "是否有基线": 0,
                "是否免考核": 0,
                "考勤范围状态":
                    NOT_INCLUDED_STATUS,
                "考勤排除原因":
                    "不在结束快照",
            })

        else:
            for field in (
                ATTENDANCE_MEMBER_FIELDS
            ):
                output[field] = attendance.get(
                    field
                )

            output["考勤范围状态"] = "纳入"
            output["考勤排除原因"] = ""

        result.append(output)

    return result


def build_compare_attendance_context(
    start_snapshot: Any,
    end_snapshot: Any,
    *,
    thresholds: Mapping[str, Any],
    weights: Mapping[str, Any] | None = None,
    enabled_metrics: Mapping[str, Any] | None = None,
    auto_disable_empty_metrics: bool = False,
    exempt_names: Iterable[str] | None = None,
    visible_compare_rows: Any = None,
) -> dict[str, Any]:
    start_rows = _normalize_snapshot_rows(
        start_snapshot,
        source_label="起始快照",
    )

    end_rows = _normalize_snapshot_rows(
        end_snapshot,
        source_label="结束快照",
    )

    dashboard = build_configurable_attendance_dashboard(
        start_rows,
        end_rows,
        thresholds=thresholds,
        weights=weights,
        enabled_metrics=enabled_metrics,
        auto_disable_empty_metrics=auto_disable_empty_metrics,
        exempt_names=exempt_names,
    )

    if visible_compare_rows is None:
        visible_rows: list[dict[str, Any]] = []
    else:
        visible_rows = enrich_compare_rows(
            visible_compare_rows,
            dashboard,
        )

    context = {
        "考勤驾驶舱": dashboard,
        "同盟概览":
            dashboard["同盟概览"],
        "分组概览":
            dashboard["分组概览"],
        "完整成员明细":
            dashboard["成员明细"],
        "当前显示明细":
            visible_rows,
        "适配契约": {
            "完整统计不受筛选影响": True,
            "同盟概览数据源":
                "完整起止快照",
            "分组概览数据源":
                "完整起止快照",
            "当前显示明细数据源":
                "页面筛选结果",
            "成员范围":
                "结束快照成员",
            "已离开成员处理":
                "保留在原对比结果时标记不计入",
        },
    }

    return _json_safe(context)

def build_compare_attendance_cache_payload(
    start_snapshot: Any,
    end_snapshot: Any,
    *,
    thresholds: Mapping[str, Any],
    weights: Mapping[str, Any] | None = None,
    enabled_metrics: Mapping[str, Any] | None = None,
    auto_disable_empty_metrics: bool = False,
    exempt_names: Iterable[str] | None = None,
    visible_compare_rows: Any = None,
) -> dict[str, Any]:
    context = build_compare_attendance_context(
        start_snapshot,
        end_snapshot,
        thresholds=thresholds,
        weights=weights,
        enabled_metrics=enabled_metrics,
        auto_disable_empty_metrics=auto_disable_empty_metrics,
        exempt_names=exempt_names,
        visible_compare_rows=visible_compare_rows,
    )

    dashboard = context["考勤驾驶舱"]

    attendance = {
        "范围": dashboard["范围"],
        "配置": dashboard["配置"],
        "同盟概览": context["同盟概览"],
        "分组概览": context["分组概览"],
        "默认排序": dashboard["默认排序"],
        "适配契约": context["适配契约"],
    }

    return _json_safe({
        "attendance": attendance,
        "visible_rows":
            context["当前显示明细"],
    })
