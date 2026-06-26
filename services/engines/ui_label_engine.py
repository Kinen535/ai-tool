from __future__ import annotations

"""
V13 - UI Label Engine

职责：
1. 统一把系统内部英文 key 转成中文显示名。
2. 不改变数据库字段。
3. 不改变 Engine 内部结构。
4. 只服务页面展示。
"""

from typing import Any, Dict


PRIORITY_LABELS = {
    "P1": "P1｜紧急",
    "P2": "P2｜重要",
    "P3": "P3｜长期",
}

STATUS_LABELS = {
    "pending": "待反馈",
    "confirmed": "已确认",
    "completed": "已完成",
    "protected": "转保护",
    "ignored": "忽略",
    "failed": "执行失败",
}

PHASE_LABELS = {
    "today": "今天",
    "tomorrow": "明天",
    "this_week": "本周",
    "season": "赛季",
}

FILTER_KEY_LABELS = {
    "priority": "优先级",
    "status": "状态",
    "phase": "阶段",
    "owner": "负责人",
}


def priority_label(value: Any) -> str:
    value = str(value or "")
    return PRIORITY_LABELS.get(value, value or "-")


def status_label(value: Any) -> str:
    value = str(value or "")
    return STATUS_LABELS.get(value, value or "-")


def phase_label(value: Any) -> str:
    value = str(value or "")
    return PHASE_LABELS.get(value, value or "-")


def filter_key_label(value: Any) -> str:
    value = str(value or "")
    return FILTER_KEY_LABELS.get(value, value or "-")


def owner_label(value: Any) -> str:
    value = str(value or "")
    return value or "未指定"


def enrich_task_labels(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    给任务增加中文展示字段，不修改原始字段。
    """
    item = dict(task)

    item["priority_label"] = priority_label(
        item.get("priority")
    )

    item["phase_label"] = phase_label(
        item.get("phase")
    )

    item["feedback_status_label"] = status_label(
        item.get("feedback_status")
    )

    item["owner_label"] = owner_label(
        item.get("owner")
    )

    return item


def value_label(kind: str, value: Any) -> str:
    if kind == "priority":
        return priority_label(value)

    if kind == "status":
        return status_label(value)

    if kind == "phase":
        return phase_label(value)

    if kind == "owner":
        return owner_label(value)

    return str(value or "-")
