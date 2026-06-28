from __future__ import annotations

from typing import Any, Dict, List


def build_leader_filter_report(
    leader_report: Dict[str, Any],
    filters: Dict[str, str],
) -> Dict[str, Any]:
    groups = leader_report.get("group_cards", []) or []

    pressure = str(filters.get("pressure") or "all").strip()
    responsibility = str(filters.get("responsibility") or "all").strip()
    sort = str(filters.get("sort") or "pressure_desc").strip()
    keyword = str(filters.get("keyword") or "").strip()

    filtered = list(groups)

    if pressure != "all":
        filtered = [
            item for item in filtered
            if item.get("pressure_level") == pressure
        ]

    if responsibility != "all":
        filtered = [
            item for item in filtered
            if item.get("responsibility_status") == responsibility
        ]

    if keyword:
        filtered = [
            item for item in filtered
            if keyword in str(item.get("group_name") or "")
            or keyword in str(item.get("leader_display") or "")
        ]

    filtered = _sort_groups(filtered, sort)

    stats = _build_filter_stats(filtered)

    return {
        "filters": {
            "pressure": pressure,
            "responsibility": responsibility,
            "sort": sort,
            "keyword": keyword,
        },
        "summary": _build_summary(filters, stats),
        "stats": stats,
        "group_cards": filtered,
        "quick_filters": _build_quick_filters(),
        "pressure_options": _pressure_options(),
        "responsibility_options": _responsibility_options(),
        "sort_options": _sort_options(),
    }


def _sort_groups(groups: List[Dict[str, Any]], sort: str) -> List[Dict[str, Any]]:
    if sort == "pressure_asc":
        return sorted(groups, key=lambda x: x.get("pressure_score", 0))

    if sort == "member_desc":
        return sorted(groups, key=lambda x: x.get("member_count", 0), reverse=True)

    if sort == "pending_desc":
        return sorted(groups, key=lambda x: x.get("pending_tasks", 0), reverse=True)

    if sort == "danger_desc":
        return sorted(groups, key=lambda x: x.get("danger_count", 0), reverse=True)

    if sort == "feedback_asc":
        return sorted(groups, key=lambda x: x.get("feedback_rate", 0))

    return sorted(groups, key=lambda x: x.get("pressure_score", 0), reverse=True)


def _build_filter_stats(groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "matched_count": len(groups),
        "high_count": len([g for g in groups if g.get("pressure_level") == "high"]),
        "medium_count": len([g for g in groups if g.get("pressure_level") == "medium"]),
        "normal_count": len([g for g in groups if g.get("pressure_level") == "normal"]),
        "unassigned_count": len([g for g in groups if g.get("responsibility_status") == "unassigned"]),
        "manual_count": len([g for g in groups if g.get("responsibility_status") == "manual"]),
        "pending_tasks": sum(g.get("pending_tasks", 0) for g in groups),
        "abnormal_tasks": sum(g.get("abnormal_tasks", 0) for g in groups),
    }


def _build_summary(filters: Dict[str, str], stats: Dict[str, Any]) -> str:
    active = []

    if filters.get("pressure", "all") != "all":
        active.append(f"压力={_label(filters.get('pressure'), _pressure_options())}")

    if filters.get("responsibility", "all") != "all":
        active.append(f"责任状态={_label(filters.get('responsibility'), _responsibility_options())}")

    if filters.get("keyword"):
        active.append(f"关键词={filters.get('keyword')}")

    if not active:
        active_text = "当前未启用筛选"
    else:
        active_text = "当前筛选：" + "，".join(active)

    return (
        f"{active_text}。共匹配 {stats.get('matched_count', 0)} 个分组，"
        f"高压 {stats.get('high_count', 0)} 个，"
        f"待指定组长 {stats.get('unassigned_count', 0)} 个，"
        f"手动指定 {stats.get('manual_count', 0)} 个。"
    )


def _label(value: str, options: List[Dict[str, str]]) -> str:
    for item in options:
        if item.get("value") == value:
            return item.get("label", value)
    return value


def _build_quick_filters() -> List[Dict[str, str]]:
    return [
        {"label": "全部分组", "url": "/leaders"},
        {"label": "高压分组", "url": "/leaders?pressure=high"},
        {"label": "待指定组长", "url": "/leaders?responsibility=unassigned"},
        {"label": "手动指定", "url": "/leaders?responsibility=manual"},
        {"label": "自动识别", "url": "/leaders?responsibility=mapped"},
        {"label": "管理代管", "url": "/leaders?responsibility=admin_proxy"},
    ]


def _pressure_options() -> List[Dict[str, str]]:
    return [
        {"value": "all", "label": "全部"},
        {"value": "high", "label": "高压"},
        {"value": "medium", "label": "关注"},
        {"value": "normal", "label": "正常"},
    ]


def _responsibility_options() -> List[Dict[str, str]]:
    return [
        {"value": "all", "label": "全部"},
        {"value": "manual", "label": "手动指定"},
        {"value": "mapped", "label": "自动识别组长"},
        {"value": "admin_proxy", "label": "管理代管"},
        {"value": "unassigned", "label": "待指定组长"},
    ]


def _sort_options() -> List[Dict[str, str]]:
    return [
        {"value": "pressure_desc", "label": "压力从高到低"},
        {"value": "pressure_asc", "label": "压力从低到高"},
        {"value": "member_desc", "label": "成员数最多"},
        {"value": "danger_desc", "label": "危险人数最多"},
        {"value": "pending_desc", "label": "待反馈最多"},
        {"value": "feedback_asc", "label": "反馈率最低"},
    ]
