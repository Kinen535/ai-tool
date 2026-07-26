from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any


SCOPE_ALLIANCE = "alliance"
SCOPE_GROUP = "group"
SCOPE_MEMBER = "member"

VALID_SCOPE_TYPES = (
    SCOPE_ALLIANCE,
    SCOPE_GROUP,
    SCOPE_MEMBER,
)


def _clean_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _as_mapping_rows(
    rows: Any,
    source_label: str,
) -> list[dict[str, Any]]:
    if rows is None:
        return []

    if hasattr(rows, "to_dict"):
        try:
            records = rows.to_dict(
                "records"
            )
        except TypeError:
            records = rows.to_dict(
                orient="records"
            )
    else:
        if isinstance(
            rows,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            raise TypeError(
                source_label
                + "不能是字符串"
            )

        if not isinstance(
            rows,
            Iterable,
        ):
            raise TypeError(
                source_label
                + "必须是可迭代记录"
            )

        records = list(rows)

    output: list[dict[str, Any]] = []

    for index, row in enumerate(records):
        if not isinstance(row, Mapping):
            raise TypeError(
                source_label
                + "第"
                + str(index + 1)
                + "行不是映射记录"
            )

        output.append(
            dict(row)
        )

    return output


def _member_name(
    row: Mapping[str, Any],
    member_key: str,
) -> str:
    return _clean_text(
        row.get(member_key)
    )


def _group_name(
    row: Mapping[str, Any],
    group_key: str,
) -> str:
    return (
        _clean_text(
            row.get(group_key)
        )
        or "未分组"
    )


def _build_member_index(
    rows: Iterable[Mapping[str, Any]],
    source_label: str,
    member_key: str,
) -> dict[str, Mapping[str, Any]]:
    index: dict[
        str,
        Mapping[str, Any],
    ] = {}

    for position, row in enumerate(
        rows,
        start=1,
    ):
        member_name = _member_name(
            row,
            member_key,
        )

        if not member_name:
            raise ValueError(
                source_label
                + "第"
                + str(position)
                + "行缺少成员名"
            )

        if member_name in index:
            raise ValueError(
                source_label
                + "存在重复成员："
                + member_name
            )

        index[member_name] = row

    return index


def normalize_compare_scope(
    scope_type: Any = SCOPE_ALLIANCE,
    scope_value: Any = None,
) -> dict[str, Any]:
    normalized_type = (
        _clean_text(scope_type).lower()
        or SCOPE_ALLIANCE
    )

    if normalized_type not in VALID_SCOPE_TYPES:
        raise ValueError(
            "不支持的分析范围："
            + normalized_type
        )

    normalized_value = _clean_text(
        scope_value
    )

    if normalized_type == SCOPE_ALLIANCE:
        normalized_value = ""
        scope_label = "全同盟"
        anchor = "complete_snapshots"

    elif normalized_type == SCOPE_GROUP:
        if not normalized_value:
            raise ValueError(
                "指定分组范围必须提供分组名"
            )

        scope_label = (
            "指定分组："
            + normalized_value
        )

        anchor = (
            "end_snapshot_membership"
        )

    else:
        if not normalized_value:
            raise ValueError(
                "指定成员范围必须提供成员名"
            )

        scope_label = (
            "指定成员："
            + normalized_value
        )

        anchor = (
            "end_snapshot_membership"
        )

    return {
        "scope_type": normalized_type,
        "scope_value": normalized_value,
        "scope_label": scope_label,
        "membership_anchor": anchor,
    }


def build_compare_scope_cache_identity(
    scope_type: Any = SCOPE_ALLIANCE,
    scope_value: Any = None,
) -> dict[str, str]:
    scope = normalize_compare_scope(
        scope_type,
        scope_value,
    )

    payload = {
        "scope_type":
            scope["scope_type"],
        "scope_value":
            scope["scope_value"],
    }

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    return {
        **payload,
        "scope_digest": digest,
        "cache_fragment": (
            "scope:"
            + payload["scope_type"]
            + ":"
            + digest[:16]
        ),
    }


def select_compare_scope_rows(
    start_rows: Any,
    end_rows: Any,
    scope_type: Any = SCOPE_ALLIANCE,
    scope_value: Any = None,
    *,
    member_key: str = "成员",
    group_key: str = "分组",
) -> dict[str, Any]:
    scope = normalize_compare_scope(
        scope_type,
        scope_value,
    )

    normalized_start = _as_mapping_rows(
        start_rows,
        "起始快照",
    )

    normalized_end = _as_mapping_rows(
        end_rows,
        "结束快照",
    )

    start_index = _build_member_index(
        normalized_start,
        "起始快照",
        member_key,
    )

    end_index = _build_member_index(
        normalized_end,
        "结束快照",
        member_key,
    )

    selected_start: list[
        dict[str, Any]
    ]

    selected_end: list[
        dict[str, Any]
    ]

    selected_member_names: list[str]

    if scope["scope_type"] == SCOPE_ALLIANCE:
        selected_start = [
            dict(row)
            for row in normalized_start
        ]

        selected_end = [
            dict(row)
            for row in normalized_end
        ]

        selected_member_names = [
            _member_name(
                row,
                member_key,
            )
            for row in selected_end
        ]

    elif scope["scope_type"] == SCOPE_GROUP:
        target_group = str(
            scope["scope_value"]
        )

        selected_end = [
            dict(row)
            for row in normalized_end
            if _group_name(
                row,
                group_key,
            ) == target_group
        ]

        if not selected_end:
            raise ValueError(
                "结束快照中没有找到分组："
                + target_group
            )

        selected_member_names = [
            _member_name(
                row,
                member_key,
            )
            for row in selected_end
        ]

        selected_names = set(
            selected_member_names
        )

        selected_start = [
            dict(row)
            for row in normalized_start
            if _member_name(
                row,
                member_key,
            ) in selected_names
        ]

    else:
        target_member = str(
            scope["scope_value"]
        )

        end_row = end_index.get(
            target_member
        )

        if end_row is None:
            raise ValueError(
                "结束快照中没有找到成员："
                + target_member
            )

        selected_end = [
            dict(end_row)
        ]

        selected_member_names = [
            target_member
        ]

        start_row = start_index.get(
            target_member
        )

        selected_start = (
            [dict(start_row)]
            if start_row is not None
            else []
        )

    selected_end_names = set(
        selected_member_names
    )

    baseline_member_count = sum(
        1
        for member_name
        in selected_member_names
        if member_name in start_index
    )

    new_member_count = (
        len(selected_member_names)
        - baseline_member_count
    )

    if scope["scope_type"] == SCOPE_ALLIANCE:
        departed_member_count = sum(
            1
            for member_name in start_index
            if member_name
            not in selected_end_names
        )
    else:
        departed_member_count = 0

    cache_identity = (
        build_compare_scope_cache_identity(
            scope["scope_type"],
            scope["scope_value"],
        )
    )

    return {
        "scope": {
            **scope,
            **cache_identity,
        },
        "start_rows": selected_start,
        "end_rows": selected_end,
        "selected_member_names":
            selected_member_names,
        "counts": {
            "start_row_count":
                len(selected_start),
            "end_row_count":
                len(selected_end),
            "selected_member_count":
                len(selected_member_names),
            "baseline_member_count":
                baseline_member_count,
            "new_member_count":
                new_member_count,
            "departed_member_count":
                departed_member_count,
        },
        "contract": {
            "scope_applied_before_dashboard":
                True,
            "detail_filters_are_separate":
                True,
            "group_and_member_use_end_snapshot":
                True,
            "input_rows_mutated":
                False,
        },
    }
