from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


STATUS_EXEMPT = "豁免"
STATUS_ANOMALY = "数据异常"
STATUS_ABSENT = "缺勤"
STATUS_BELOW = "未达标"
STATUS_QUALIFIED = "合格"

OVERALL_EXEMPT = "豁免"
OVERALL_ANOMALY = "数据异常"
OVERALL_ABSENT = "全项缺勤"
OVERALL_IMPROVE = "待改进"
OVERALL_QUALIFIED = "全部合格"

METRICS = (
    {
        "code": "battle",
        "label": "战功",
        "total_key": "战功总量",
        "growth_key": "战功增长",
    },
    {
        "code": "assist",
        "label": "助攻",
        "total_key": "助攻总量",
        "growth_key": "助攻增长",
    },
    {
        "code": "donate",
        "label": "捐献",
        "total_key": "捐献总量",
        "growth_key": "捐献增长",
    },
)

OVERALL_PRIORITY = {
    OVERALL_ANOMALY: 0,
    OVERALL_ABSENT: 1,
    OVERALL_IMPROVE: 2,
    OVERALL_QUALIFIED: 3,
    OVERALL_EXEMPT: 4,
}


def _to_number(value: Any) -> int | float:
    if value is None or value == "":
        return 0

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace(",", "")

        if not text:
            return 0

        try:
            number = float(text)
        except ValueError as error:
            raise ValueError(
                f"无法转换为数字：{value!r}"
            ) from error

    if number.is_integer():
        return int(number)

    return number


def _is_truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "是",
            "豁免",
            "免考核",
        }

    return bool(value)


def _resolve_metric_values(
    values: Mapping[str, Any],
    *,
    label: str,
    allow_zero_total: bool,
) -> dict[str, float]:
    result: dict[str, float] = {}

    for metric in METRICS:
        code = metric["code"]
        chinese_label = metric["label"]

        if code in values:
            raw_value = values[code]
        elif chinese_label in values:
            raw_value = values[chinese_label]
        else:
            raise ValueError(
                f"{label}缺少{chinese_label}配置"
            )

        number = float(_to_number(raw_value))

        if number < 0:
            raise ValueError(
                f"{chinese_label}{label}不能小于0"
            )

        result[code] = number

    total = sum(result.values())

    if not allow_zero_total and total <= 0:
        raise ValueError(
            f"{label}总和必须大于0"
        )

    return result


def normalize_thresholds(
    thresholds: Mapping[str, Any],
) -> dict[str, float]:
    return _resolve_metric_values(
        thresholds,
        label="考核标准",
        allow_zero_total=True,
    )


def normalize_weights(
    weights: Mapping[str, Any] | None,
) -> dict[str, float]:
    if weights is None:
        return {
            "battle": 1 / 3,
            "assist": 1 / 3,
            "donate": 1 / 3,
        }

    values = _resolve_metric_values(
        weights,
        label="权重",
        allow_zero_total=False,
    )

    total = sum(values.values())

    return {
        code: value / total
        for code, value in values.items()
    }


def classify_growth(
    growth: Any,
    threshold: Any,
    *,
    exempt: bool = False,
) -> str:
    if exempt:
        return STATUS_EXEMPT

    growth_value = float(_to_number(growth))
    threshold_value = float(_to_number(threshold))

    if threshold_value < 0:
        raise ValueError(
            "考核标准不能小于0"
        )

    if growth_value < 0:
        return STATUS_ANOMALY

    if growth_value == 0:
        return STATUS_ABSENT

    if growth_value < threshold_value:
        return STATUS_BELOW

    return STATUS_QUALIFIED


def _index_snapshot(
    rows: Iterable[Mapping[str, Any]],
    *,
    member_key: str,
    snapshot_label: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for source_row in rows:
        row = dict(source_row)
        member_name = str(
            row.get(member_key, "")
            or ""
        ).strip()

        if not member_name:
            raise ValueError(
                f"{snapshot_label}存在空成员名"
            )

        if member_name in result:
            raise ValueError(
                f"{snapshot_label}存在重复成员："
                f"{member_name}"
            )

        result[member_name] = row

    return result


def _build_member_result(
    member_name: str,
    start_row: Mapping[str, Any],
    end_row: Mapping[str, Any],
    *,
    thresholds: Mapping[str, float],
    exempt: bool,
    group_key: str,
) -> dict[str, Any]:
    result = dict(end_row)

    result["成员"] = member_name
    result["分组"] = str(
        end_row.get(group_key, "")
        or "未分组"
    ).strip() or "未分组"

    statuses: list[str] = []
    qualified_count = 0
    abnormal_count = 0
    failed_count = 0

    for metric in METRICS:
        code = metric["code"]
        label = metric["label"]
        total_key = metric["total_key"]
        growth_key = metric["growth_key"]

        start_total = _to_number(
            start_row.get(total_key, 0)
        )

        end_total = _to_number(
            end_row.get(total_key, 0)
        )

        growth = _to_number(
            end_total - start_total
        )

        status = classify_growth(
            growth,
            thresholds[code],
            exempt=exempt,
        )

        result[growth_key] = growth
        result[f"{label}考勤状态"] = status
        result[f"{label}考核标准"] = thresholds[code]

        statuses.append(status)

        if status == STATUS_QUALIFIED:
            qualified_count += 1
        elif status == STATUS_ANOMALY:
            abnormal_count += 1
        elif status in {
            STATUS_ABSENT,
            STATUS_BELOW,
        }:
            failed_count += 1

    if exempt:
        overall_status = OVERALL_EXEMPT
    elif abnormal_count > 0:
        overall_status = OVERALL_ANOMALY
    elif qualified_count == len(METRICS):
        overall_status = OVERALL_QUALIFIED
    elif all(
        status == STATUS_ABSENT
        for status in statuses
    ):
        overall_status = OVERALL_ABSENT
    else:
        overall_status = OVERALL_IMPROVE

    result["综合考勤状态"] = overall_status
    result["考勤排序等级"] = (
        OVERALL_PRIORITY[overall_status]
    )
    result["合格项数"] = qualified_count
    result["未达标项数"] = failed_count
    result["异常项数"] = abnormal_count
    result["是否免考核"] = 1 if exempt else 0

    return result


def _build_metric_summary(
    members: list[dict[str, Any]],
    metric: Mapping[str, str],
) -> dict[str, Any]:
    label = metric["label"]
    growth_key = metric["growth_key"]
    status_key = f"{label}考勤状态"

    assessed = [
        member
        for member in members
        if member[status_key] != STATUS_EXEMPT
    ]

    valid = [
        member
        for member in assessed
        if member[status_key] != STATUS_ANOMALY
    ]

    qualified = [
        member
        for member in valid
        if member[status_key] == STATUS_QUALIFIED
    ]

    below = [
        member
        for member in valid
        if member[status_key] == STATUS_BELOW
    ]

    absent = [
        member
        for member in valid
        if member[status_key] == STATUS_ABSENT
    ]

    anomaly = [
        member
        for member in assessed
        if member[status_key] == STATUS_ANOMALY
    ]

    active = [
        member
        for member in valid
        if float(_to_number(member[growth_key])) > 0
    ]

    total_growth = sum(
        float(_to_number(member[growth_key]))
        for member in valid
    )

    valid_count = len(valid)

    qualified_rate = (
        len(qualified) / valid_count * 100
        if valid_count
        else 0
    )

    participation_rate = (
        len(active) / valid_count * 100
        if valid_count
        else 0
    )

    highest_member = ""
    highest_growth: int | float = 0

    if valid:
        highest = sorted(
            valid,
            key=lambda member: (
                -float(
                    _to_number(
                        member[growth_key]
                    )
                ),
                str(member["成员"]),
            ),
        )[0]

        highest_member = str(
            highest["成员"]
        )

        highest_growth = _to_number(
            highest[growth_key]
        )

    return {
        "指标": label,
        "考核人数": len(assessed),
        "有效考核人数": valid_count,
        "豁免人数": (
            len(members) - len(assessed)
        ),
        "参与人数": len(active),
        "参与率": round(participation_rate, 1),
        "合格人数": len(qualified),
        "合格率": round(qualified_rate, 1),
        "缺勤人数": len(absent),
        "未达标人数": len(below),
        "数据异常人数": len(anomaly),
        "总增长": _to_number(total_growth),
        "人均增长": (
            round(total_growth / valid_count, 1)
            if valid_count
            else 0
        ),
        "最高成员": highest_member,
        "最高增长": highest_growth,
        "缺勤名单": sorted(
            str(member["成员"])
            for member in absent
        ),
        "未达标名单": sorted(
            str(member["成员"])
            for member in below
        ),
        "数据异常名单": sorted(
            str(member["成员"])
            for member in anomaly
        ),
    }


def _build_scope_summary(
    members: list[dict[str, Any]],
    weights: Mapping[str, float],
) -> dict[str, Any]:
    metrics: dict[str, dict[str, Any]] = {}

    for metric in METRICS:
        metrics[metric["code"]] = (
            _build_metric_summary(
                members,
                metric,
            )
        )

    assessed_names = {
        str(member["成员"])
        for member in members
        if not member["是否免考核"]
    }

    exempt_names = sorted(
        str(member["成员"])
        for member in members
        if member["是否免考核"]
    )

    comprehensive_score = sum(
        metrics[metric["code"]]["合格率"]
        * weights[metric["code"]]
        for metric in METRICS
    )

    return {
        "总人数": len(members),
        "考核人数": len(assessed_names),
        "豁免人数": len(exempt_names),
        "豁免名单": exempt_names,
        "战功": metrics["battle"],
        "助攻": metrics["assist"],
        "捐献": metrics["donate"],
        "综合考勤分": round(
            comprehensive_score,
            1,
        ),
    }


def _assign_group_ranks(
    groups: list[dict[str, Any]],
    value_key: str,
    rank_key: str,
) -> None:
    ordered = sorted(
        groups,
        key=lambda group: (
            -float(group[value_key]),
            str(group["分组"]),
        ),
    )

    previous_value: float | None = None
    current_rank = 0

    for position, group in enumerate(
        ordered,
        start=1,
    ):
        value = float(group[value_key])

        if (
            previous_value is None
            or value != previous_value
        ):
            current_rank = position
            previous_value = value

        group[rank_key] = current_rank


def build_attendance_dashboard(
    start_rows: Iterable[Mapping[str, Any]],
    end_rows: Iterable[Mapping[str, Any]],
    *,
    thresholds: Mapping[str, Any],
    weights: Mapping[str, Any] | None = None,
    exempt_names: Iterable[str] | None = None,
    member_key: str = "成员",
    group_key: str = "分组",
    exempt_field: str = "免考核",
) -> dict[str, Any]:
    normalized_thresholds = (
        normalize_thresholds(thresholds)
    )

    normalized_weights = normalize_weights(
        weights
    )

    start_index = _index_snapshot(
        start_rows,
        member_key=member_key,
        snapshot_label="起始快照",
    )

    end_index = _index_snapshot(
        end_rows,
        member_key=member_key,
        snapshot_label="结束快照",
    )

    exemption_set = {
        str(name).strip()
        for name in (exempt_names or [])
        if str(name).strip()
    }

    members: list[dict[str, Any]] = []

    for member_name, end_row in end_index.items():
        start_row = start_index.get(
            member_name,
            {},
        )

        exempt = (
            member_name in exemption_set
            or _is_truthy(
                end_row.get(
                    exempt_field,
                    False,
                )
            )
        )

        members.append(
            _build_member_result(
                member_name,
                start_row,
                end_row,
                thresholds=normalized_thresholds,
                exempt=exempt,
                group_key=group_key,
            )
        )

    members.sort(
        key=lambda member: (
            int(member["考勤排序等级"]),
            float(_to_number(member["战功增长"])),
            float(_to_number(member["助攻增长"])),
            float(_to_number(member["捐献增长"])),
            str(member["成员"]),
        )
    )

    alliance_overview = _build_scope_summary(
        members,
        normalized_weights,
    )

    grouped_members: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for member in members:
        group_name = str(
            member["分组"]
        )

        grouped_members.setdefault(
            group_name,
            [],
        ).append(member)

    group_overview: list[dict[str, Any]] = []

    for group_name, group_members in (
        grouped_members.items()
    ):
        summary = _build_scope_summary(
            group_members,
            normalized_weights,
        )

        summary["分组"] = group_name
        summary["战功合格率"] = (
            summary["战功"]["合格率"]
        )
        summary["助攻合格率"] = (
            summary["助攻"]["合格率"]
        )
        summary["捐献合格率"] = (
            summary["捐献"]["合格率"]
        )

        group_overview.append(summary)

    _assign_group_ranks(
        group_overview,
        "战功合格率",
        "战功排名",
    )

    _assign_group_ranks(
        group_overview,
        "助攻合格率",
        "助攻排名",
    )

    _assign_group_ranks(
        group_overview,
        "捐献合格率",
        "捐献排名",
    )

    _assign_group_ranks(
        group_overview,
        "综合考勤分",
        "综合排名",
    )

    group_overview.sort(
        key=lambda group: (
            int(group["综合排名"]),
            str(group["分组"]),
        )
    )

    start_names = set(start_index)
    end_names = set(end_index)

    return {
        "范围": {
            "起始快照人数": len(start_names),
            "结束快照人数": len(end_names),
            "匹配成员数": len(
                start_names & end_names
            ),
            "新增成员数": len(
                end_names - start_names
            ),
            "离开成员数": len(
                start_names - end_names
            ),
            "新增成员名单": sorted(
                end_names - start_names
            ),
            "离开成员名单": sorted(
                start_names - end_names
            ),
            "考勤分母规则":
                "仅统计结束快照成员",
        },
        "配置": {
            "考核标准":
                dict(normalized_thresholds),
            "权重":
                dict(normalized_weights),
        },
        "同盟概览": alliance_overview,
        "分组概览": group_overview,
        "成员明细": members,
        "默认排序": {
            "模式": "异常优先",
            "字段": "考勤排序等级",
            "方向": "升序",
            "次级字段": [
                "战功增长",
                "助攻增长",
                "捐献增长",
                "成员",
            ],
        },
    }
