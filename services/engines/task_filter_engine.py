from __future__ import annotations

"""
V13 - Task Filter Engine

职责：
1. 负责 /tasks 页面任务筛选。
2. 支持普通筛选：priority / status / phase / owner。
3. 支持快捷筛选 preset。
4. 支持任务排序 sort。
5. 只消费 report["v12_execution_feedback"]。
6. 不访问数据库。
7. 不调用 LLM。
8. 不修改 V12 反馈状态。
9. 输出中文展示 label，但保留内部英文 value。
"""

from typing import Any, Dict, List

from services.engines.ui_label_engine import (
    enrich_task_labels,
    filter_key_label,
    value_label,
)


PRESET_LABELS = {
    "all": "全部任务",
    "urgent_pending": "紧急待反馈",
    "today": "今日任务",
    "this_week": "本周任务",
    "failed": "执行失败",
    "protected": "转保护",
    "abnormal": "异常反馈",
    "leader_owner": "所属组长任务",
}


SORT_LABELS = {
    "smart": "智能排序",
    "priority": "按优先级",
    "phase": "按阶段",
    "status": "按状态",
    "owner": "按负责人",
}


PRIORITY_ORDER = {
    "P1": 1,
    "P2": 2,
    "P3": 3,
}


PHASE_ORDER = {
    "today": 1,
    "tomorrow": 2,
    "this_week": 3,
    "season": 4,
}


STATUS_ORDER = {
    "pending": 1,
    "failed": 2,
    "ignored": 3,
    "protected": 4,
    "completed": 5,
    "confirmed": 6,
}


def build_task_filter_report(
    report: Dict[str, Any],
    filters: Dict[str, str],
) -> Dict[str, Any]:
    fb = report.get("v12_execution_feedback", {}) or {}
    raw_tasks = fb.get("tasks", []) or []

    tasks = [
        enrich_task_labels(task)
        for task in raw_tasks
    ]

    normalized_filters = _normalize_filters(filters)

    filtered_tasks = [
        task for task in tasks
        if _match_task(task, normalized_filters)
    ]

    sorted_tasks = _sort_tasks(
        filtered_tasks,
        normalized_filters.get("sort", "smart"),
    )

    pending_tasks = [
        task for task in sorted_tasks
        if task.get("feedback_status") == "pending"
    ]

    done_tasks = [
        task for task in sorted_tasks
        if task.get("feedback_status") != "pending"
    ]

    options = _build_filter_options(tasks)
    stats = _build_filtered_stats(sorted_tasks)

    return {
        "filters": normalized_filters,
        "options": options,
        "filtered_tasks": sorted_tasks,
        "pending_tasks": pending_tasks,
        "done_tasks": done_tasks,
        "stats": stats,
        "summary": _build_summary(
            sorted_tasks,
            pending_tasks,
            done_tasks,
            normalized_filters,
        ),
        "quick_filters": _build_quick_filters(),
    }


def _normalize_filters(filters: Dict[str, str]) -> Dict[str, str]:
    return {
        "priority": (filters.get("priority") or "all").strip(),
        "status": (filters.get("status") or "all").strip(),
        "phase": (filters.get("phase") or "all").strip(),
        "owner": (filters.get("owner") or "all").strip(),
        "preset": (filters.get("preset") or "all").strip(),
        "sort": (filters.get("sort") or "smart").strip(),
    }


def _match_task(
    task: Dict[str, Any],
    filters: Dict[str, str],
) -> bool:
    if not _match_preset(task, filters.get("preset", "all")):
        return False

    if filters.get("priority") != "all":
        if task.get("priority") != filters.get("priority"):
            return False

    if filters.get("status") != "all":
        if task.get("feedback_status") != filters.get("status"):
            return False

    if filters.get("phase") != "all":
        if task.get("phase") != filters.get("phase"):
            return False

    if filters.get("owner") != "all":
        if task.get("owner") != filters.get("owner"):
            return False

    return True


def _match_preset(
    task: Dict[str, Any],
    preset: str,
) -> bool:
    if preset in ("", "all"):
        return True

    if preset == "urgent_pending":
        return (
            task.get("priority") == "P1"
            and task.get("feedback_status") == "pending"
        )

    if preset == "today":
        return task.get("phase") == "today"

    if preset == "this_week":
        return task.get("phase") == "this_week"

    if preset == "failed":
        return task.get("feedback_status") == "failed"

    if preset == "protected":
        return task.get("feedback_status") == "protected"

    if preset == "abnormal":
        return task.get("feedback_status") in ("ignored", "failed")

    if preset == "leader_owner":
        return task.get("owner") == "所属组长"

    return True


def _sort_tasks(
    tasks: List[Dict[str, Any]],
    sort_mode: str,
) -> List[Dict[str, Any]]:
    if sort_mode == "priority":
        return sorted(tasks, key=_priority_sort_key)

    if sort_mode == "phase":
        return sorted(tasks, key=_phase_sort_key)

    if sort_mode == "status":
        return sorted(tasks, key=_status_sort_key)

    if sort_mode == "owner":
        return sorted(tasks, key=_owner_sort_key)

    return sorted(tasks, key=_smart_sort_key)


def _smart_sort_key(task: Dict[str, Any]):
    return (
        PRIORITY_ORDER.get(task.get("priority"), 99),
        PHASE_ORDER.get(task.get("phase"), 99),
        STATUS_ORDER.get(task.get("feedback_status"), 99),
        task.get("owner") or "",
        task.get("target") or "",
    )


def _priority_sort_key(task: Dict[str, Any]):
    return (
        PRIORITY_ORDER.get(task.get("priority"), 99),
        PHASE_ORDER.get(task.get("phase"), 99),
        STATUS_ORDER.get(task.get("feedback_status"), 99),
        task.get("target") or "",
    )


def _phase_sort_key(task: Dict[str, Any]):
    return (
        PHASE_ORDER.get(task.get("phase"), 99),
        PRIORITY_ORDER.get(task.get("priority"), 99),
        STATUS_ORDER.get(task.get("feedback_status"), 99),
        task.get("target") or "",
    )


def _status_sort_key(task: Dict[str, Any]):
    return (
        STATUS_ORDER.get(task.get("feedback_status"), 99),
        PRIORITY_ORDER.get(task.get("priority"), 99),
        PHASE_ORDER.get(task.get("phase"), 99),
        task.get("target") or "",
    )


def _owner_sort_key(task: Dict[str, Any]):
    return (
        task.get("owner") or "",
        PRIORITY_ORDER.get(task.get("priority"), 99),
        PHASE_ORDER.get(task.get("phase"), 99),
        STATUS_ORDER.get(task.get("feedback_status"), 99),
        task.get("target") or "",
    )


def _build_quick_filters() -> List[Dict[str, str]]:
    return [
        {"key": "all", "label": "全部任务", "url": "/tasks"},
        {"key": "urgent_pending", "label": "紧急待反馈", "url": "/tasks?preset=urgent_pending"},
        {"key": "today", "label": "今日任务", "url": "/tasks?preset=today"},
        {"key": "this_week", "label": "本周任务", "url": "/tasks?preset=this_week"},
        {"key": "failed", "label": "执行失败", "url": "/tasks?preset=failed"},
        {"key": "protected", "label": "转保护", "url": "/tasks?preset=protected"},
        {"key": "abnormal", "label": "异常反馈", "url": "/tasks?preset=abnormal"},
        {"key": "leader_owner", "label": "所属组长任务", "url": "/tasks?preset=leader_owner"},
    ]


def _build_filter_options(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    priorities = _unique_sorted([
        task.get("priority")
        for task in tasks
        if task.get("priority")
    ])

    phases = _unique_sorted([
        task.get("phase")
        for task in tasks
        if task.get("phase")
    ])

    owners = _unique_sorted([
        task.get("owner")
        for task in tasks
        if task.get("owner")
    ])

    return {
        "priorities": [
            {"value": item, "label": value_label("priority", item)}
            for item in priorities
        ],
        "statuses": [
            {"value": "pending", "label": "待反馈"},
            {"value": "confirmed", "label": "已确认"},
            {"value": "completed", "label": "已完成"},
            {"value": "protected", "label": "转保护"},
            {"value": "ignored", "label": "忽略"},
            {"value": "failed", "label": "执行失败"},
        ],
        "phases": [
            {"value": item, "label": value_label("phase", item)}
            for item in phases
        ],
        "owners": [
            {"value": item, "label": value_label("owner", item)}
            for item in owners
        ],
        "sorts": [
            {"value": "smart", "label": "智能排序"},
            {"value": "priority", "label": "按优先级"},
            {"value": "phase", "label": "按阶段"},
            {"value": "status", "label": "按状态"},
            {"value": "owner", "label": "按负责人"},
        ],
    }


def _build_filtered_stats(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(tasks)

    pending = sum(
        1 for task in tasks
        if task.get("feedback_status") == "pending"
    )

    done = total - pending

    p1_total = sum(
        1 for task in tasks
        if task.get("priority") == "P1"
    )

    p1_done = sum(
        1 for task in tasks
        if task.get("priority") == "P1"
        and task.get("feedback_status") != "pending"
    )

    abnormal = sum(
        1 for task in tasks
        if task.get("feedback_status") in ("ignored", "failed")
    )

    positive = sum(
        1 for task in tasks
        if task.get("feedback_status") in ("confirmed", "completed", "protected")
    )

    return {
        "total": total,
        "pending": pending,
        "done": done,
        "p1_total": p1_total,
        "p1_done": p1_done,
        "positive": positive,
        "abnormal": abnormal,
        "feedback_rate": round(done / total, 2) if total else 0,
        "p1_feedback_rate": round(p1_done / p1_total, 2) if p1_total else 0,
    }


def _build_summary(
    filtered_tasks: List[Dict[str, Any]],
    pending_tasks: List[Dict[str, Any]],
    done_tasks: List[Dict[str, Any]],
    filters: Dict[str, str],
) -> str:
    active_filters = []

    preset = filters.get("preset", "all")

    if preset != "all":
        active_filters.append(
            f"快捷入口={PRESET_LABELS.get(preset, preset)}"
        )

    for key, value in filters.items():
        if key in ("preset", "sort"):
            continue

        if value != "all":
            active_filters.append(
                f"{filter_key_label(key)}={value_label(key, value)}"
            )

    sort_mode = filters.get("sort", "smart")
    sort_label = SORT_LABELS.get(sort_mode, "智能排序")

    if active_filters:
        prefix = "当前筛选：" + "，".join(active_filters)
    else:
        prefix = "当前未启用筛选"

    return (
        f"{prefix}。"
        f"排序方式：{sort_label}。"
        f"共匹配 {len(filtered_tasks)} 项任务，"
        f"待反馈 {len(pending_tasks)} 项，"
        f"已反馈 {len(done_tasks)} 项。"
    )


def _unique_sorted(values: List[str]) -> List[str]:
    return sorted(set(values))
