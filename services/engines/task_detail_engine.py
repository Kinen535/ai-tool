from __future__ import annotations

"""
V13 - Task Detail Engine

职责：
1. 根据 task_key 从 V12 任务池中定位单个任务。
2. 组装任务详情页需要的结构化数据。
3. 只消费 report 与反馈日志。
4. 不访问数据库。
5. 不调用 LLM。
6. 不修改任务状态。
"""

from typing import Any, Dict, List

from services.engines.ui_label_engine import (
    enrich_task_labels,
)


def build_task_detail_report(
    report: Dict[str, Any],
    task_key: str,
    logs: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    fb = report.get("v12_execution_feedback", {}) or {}
    tasks = fb.get("tasks", []) or []

    task = None

    for item in tasks:
        if item.get("task_key") == task_key:
            task = enrich_task_labels(item)
            break

    if not task:
        return {
            "found": False,
            "task_key": task_key,
            "summary": "未找到该任务，可能任务已随快照变化而更新。",
            "task": {},
            "logs": [],
            "decision": {
                "label": "任务不存在",
                "reason": "当前 V12 执行任务池中没有匹配的 task_key。",
            },
        }

    normalized_logs = [
        _normalize_log(log)
        for log in (logs or [])
    ]

    return {
        "found": True,
        "task_key": task_key,
        "summary": _build_summary(task, normalized_logs),
        "task": task,
        "logs": normalized_logs,
        "facts": _build_facts(task, normalized_logs),
        "decision": _build_decision(task, normalized_logs),
        "execution": _build_execution(task),
        "review": _build_review(task),
    }


def _normalize_log(log: Dict[str, Any]) -> Dict[str, Any]:
    old_status = log.get("old_status") or ""
    new_status = log.get("new_status") or ""

    feedback_note = log.get("feedback_note") or ""

    return {
        "created_at": log.get("created_at") or "",
        "target": log.get("target") or "",
        "task_title": log.get("task_title") or "",
        "old_status": old_status,
        "new_status": new_status,
        "old_label": _status_label(old_status),
        "new_label": _status_label(new_status),
        "change_label": _build_change_label(
            old_status,
            new_status,
            feedback_note
        ),
        "change_level": _build_change_level(
            old_status,
            new_status,
            feedback_note
        ),
        "change_level_label": _build_change_level_label(
            old_status,
            new_status,
            feedback_note
        ),
        "feedback_note": feedback_note,
    }


def _build_change_level(
    old_status: str,
    new_status: str,
    feedback_note: str = "",
) -> str:
    if old_status == new_status:
        if feedback_note:
            return "note"
        return "repeat"

    if new_status in ("confirmed", "completed"):
        return "positive"

    if new_status == "protected":
        return "protected"

    if new_status in ("failed", "ignored"):
        return "abnormal"

    if new_status == "pending":
        return "pending"

    return "normal"


def _build_change_level_label(
    old_status: str,
    new_status: str,
    feedback_note: str = "",
) -> str:
    level = _build_change_level(
        old_status,
        new_status,
        feedback_note
    )

    labels = {
        "note": "备注",
        "repeat": "重复",
        "positive": "正向",
        "protected": "保护",
        "abnormal": "异常",
        "pending": "待处理",
        "normal": "变化",
    }

    return labels.get(level, "变化")


def _build_change_label(
    old_status: str,
    new_status: str,
    feedback_note: str = "",
) -> str:
    old_label = _status_label(old_status)
    new_label = _status_label(new_status)

    if old_status == new_status:
        if feedback_note:
            return f"备注补充（{new_label}）"

        return f"重复反馈（{new_label}）"

    return f"{old_label} → {new_label}"


def _build_summary(
    task: Dict[str, Any],
    logs: List[Dict[str, Any]],
) -> str:
    return (
        f"当前任务「{task.get('title')}」对象为「{task.get('target')}」，"
        f"状态为「{task.get('feedback_status_label')}」，"
        f"累计反馈变更 {len(logs)} 次。"
    )


def _build_facts(
    task: Dict[str, Any],
    logs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "priority": task.get("priority_label"),
        "phase": task.get("phase_label"),
        "owner": task.get("owner_label"),
        "status": task.get("feedback_status_label"),
        "log_count": len(logs),
        "target": task.get("target"),
    }


def _build_decision(
    task: Dict[str, Any],
    logs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    status = task.get("feedback_status")

    if status == "pending":
        return {
            "label": "等待反馈",
            "reason": "该任务尚未收到执行反馈，需要负责人确认处理结果。",
            "level": "warning",
        }

    if status in ("failed", "ignored"):
        return {
            "label": "需要复核",
            "reason": "该任务存在异常反馈，应由管理层确认是否需要重新分配或调整执行方式。",
            "level": "danger",
        }

    if status == "protected":
        return {
            "label": "保护复核",
            "reason": "该任务已转入保护状态，需要确认保护原因是否明确。",
            "level": "info",
        }

    return {
        "label": "反馈正常",
        "reason": "该任务已有有效反馈，可作为后续复盘依据。",
        "level": "safe",
    }


def _build_execution(task: Dict[str, Any]) -> List[str]:
    status = task.get("feedback_status")

    if status == "pending":
        return [
            "联系负责人确认任务是否已经执行。",
            "若任务今日内仍未反馈，纳入催办列表。",
            "必要时由管理层接手确认。",
        ]

    if status in ("failed", "ignored"):
        return [
            "确认失败或忽略原因是否合理。",
            "判断该任务是否需要重新分配负责人。",
            "将异常反馈纳入复盘依据。",
        ]

    if status == "protected":
        return [
            "确认保护对象的身份或战略用途。",
            "补充保护原因，避免后续误清。",
            "必要时同步到身份中心或保护名单。",
        ]

    return [
        "保留当前反馈记录。",
        "等待下一轮快照验证执行结果。",
        "将任务反馈提供给 Reflection / Learning 使用。",
    ]


def _build_review(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "next_check": "下一次快照 / 下一次任务中心刷新",
        "success_condition": "任务状态有明确反馈，且后续风险数据出现改善。",
        "failure_condition": "任务长期无反馈、反馈异常增加，或后续风险没有改善。",
    }


def _status_label(value: str) -> str:
    labels = {
        "pending": "待反馈",
        "confirmed": "已确认",
        "completed": "已完成",
        "protected": "转保护",
        "ignored": "忽略",
        "failed": "执行失败",
    }

    return labels.get(value, value or "-")
