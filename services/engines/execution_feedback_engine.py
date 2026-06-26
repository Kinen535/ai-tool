from __future__ import annotations

"""
V12 - Execution Feedback Engine

职责：
1. 基于 V11 Execution Planner 的任务列表与 V12 反馈记录生成反馈分析。
2. 不访问数据库。
3. 不调用 LLM。
4. 不修改原始 report。
5. staff_engine 只负责调度。
"""

from typing import Any, Dict, List

from services.v12_feedback_store import (
    build_task_key,
    get_feedback_map,
)


ALL_STATUSES = [
    "pending",
    "confirmed",
    "completed",
    "protected",
    "ignored",
    "failed",
]


STATUS_LABELS = {
    "pending": "待反馈",
    "confirmed": "已确认",
    "completed": "已完成",
    "protected": "转保护",
    "ignored": "未处理",
    "failed": "执行失败",
}


def build_execution_feedback_report(report: Dict[str, Any]) -> Dict[str, Any]:
    execution_plan = report.get("v11_execution_plan", {}) or {}
    phases = execution_plan.get("phases", {}) or {}

    feedback_records = report.get("v12_feedback_records", []) or []
    feedback_map = get_feedback_map(feedback_records)

    tasks = _collect_tasks(phases, feedback_map)

    stats = _build_feedback_stats(tasks)
    phase_stats = _build_phase_stats(tasks)
    owner_stats = _build_owner_stats(tasks)

    decision = _build_decision(stats)
    summary = _build_summary(stats, decision)

    done_statuses = (
        "confirmed",
        "completed",
        "protected",
        "ignored",
        "failed",
    )

    return {
        "summary": summary,
        "stats": stats,
        "phase_stats": phase_stats,
        "owner_stats": owner_stats,
        "tasks": tasks,
        "pending_tasks": [
            task for task in tasks
            if task.get("feedback_status") == "pending"
        ],
        "confirmed_tasks": [
            task for task in tasks
            if task.get("feedback_status") in done_statuses
        ],
        "abnormal_feedback_tasks": [
            task for task in tasks
            if task.get("feedback_status") in ("ignored", "failed")
        ],
        "risk_tasks": [
            task for task in tasks
            if task.get("phase") == "today"
            and task.get("feedback_status") in ("pending", "ignored", "failed")
        ],
        "decision": decision,
        "execution": _build_execution(stats),
        "review": {
            "next_check": "下一次 /strategic 刷新或下一次快照",
            "success_condition": "今日任务反馈率提升，关键 P1 任务有明确处理结果。",
            "failure_condition": "P1 任务长期 pending，组长无反馈，导致复盘无法判断策略是否落地。",
        },
    }


def _collect_tasks(
    phases: Dict[str, List[Dict[str, Any]]],
    feedback_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []

    phase_order = [
        "today",
        "tomorrow",
        "this_week",
        "season",
    ]

    for phase in phase_order:
        for task in phases.get(phase, []) or []:
            task_key = build_task_key(task)
            feedback = feedback_map.get(task_key, {}) or {}

            status = feedback.get("status") or "pending"

            item = dict(task)
            item["task_key"] = task_key
            item["feedback_status"] = status
            item["feedback_label"] = STATUS_LABELS.get(status, status)
            item["feedback_note"] = feedback.get("feedback_note", "")
            item["feedback_updated_at"] = feedback.get("updated_at", "")

            result.append(item)

    return result


def _build_feedback_stats(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(tasks)

    counts = {
        status: 0
        for status in ALL_STATUSES
    }

    done_statuses = (
        "confirmed",
        "completed",
        "protected",
        "ignored",
        "failed",
    )

    positive_statuses = (
        "confirmed",
        "completed",
        "protected",
    )

    abnormal_statuses = (
        "ignored",
        "failed",
    )

    p1_total = 0
    p1_done = 0

    for task in tasks:
        status = task.get("feedback_status", "pending")
        counts[status] = counts.get(status, 0) + 1

        if task.get("priority") == "P1":
            p1_total += 1

            if status in done_statuses:
                p1_done += 1

    done_count = sum(
        counts.get(status, 0)
        for status in done_statuses
    )

    positive_count = sum(
        counts.get(status, 0)
        for status in positive_statuses
    )

    abnormal_count = sum(
        counts.get(status, 0)
        for status in abnormal_statuses
    )

    feedback_rate = round(done_count / total, 2) if total else 0
    p1_feedback_rate = round(p1_done / p1_total, 2) if p1_total else 0

    return {
        "total_tasks": total,
        "pending_count": counts.get("pending", 0),
        "confirmed_count": counts.get("confirmed", 0),
        "completed_count": counts.get("completed", 0),
        "protected_count": counts.get("protected", 0),
        "ignored_count": counts.get("ignored", 0),
        "failed_count": counts.get("failed", 0),
        "done_count": done_count,
        "positive_count": positive_count,
        "abnormal_count": abnormal_count,
        "feedback_rate": feedback_rate,
        "p1_total": p1_total,
        "p1_done": p1_done,
        "p1_feedback_rate": p1_feedback_rate,
    }


def _build_phase_stats(tasks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}

    done_statuses = (
        "confirmed",
        "completed",
        "protected",
        "ignored",
        "failed",
    )

    for task in tasks:
        phase = task.get("phase", "unknown")
        status = task.get("feedback_status", "pending")

        if phase not in result:
            result[phase] = {
                "total": 0,
                "done": 0,
                "pending": 0,
            }

        result[phase]["total"] += 1

        if status in done_statuses:
            result[phase]["done"] += 1
        else:
            result[phase]["pending"] += 1

    for phase, item in result.items():
        total = item.get("total", 0)
        done = item.get("done", 0)
        item["feedback_rate"] = round(done / total, 2) if total else 0

    return result


def _build_owner_stats(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    temp: Dict[str, Dict[str, Any]] = {}

    done_statuses = (
        "confirmed",
        "completed",
        "protected",
        "ignored",
        "failed",
    )

    for task in tasks:
        owner = task.get("owner") or "未指定"
        status = task.get("feedback_status", "pending")

        if owner not in temp:
            temp[owner] = {
                "owner": owner,
                "total": 0,
                "done": 0,
                "pending": 0,
            }

        temp[owner]["total"] += 1

        if status in done_statuses:
            temp[owner]["done"] += 1
        else:
            temp[owner]["pending"] += 1

    result = []

    for item in temp.values():
        total = item.get("total", 0)
        done = item.get("done", 0)
        item["feedback_rate"] = round(done / total, 2) if total else 0
        result.append(item)

    result.sort(
        key=lambda x: (x.get("pending", 0), x.get("total", 0)),
        reverse=True,
    )

    return result


def _build_decision(stats: Dict[str, Any]) -> Dict[str, Any]:
    total = stats.get("total_tasks", 0)
    feedback_rate = stats.get("feedback_rate", 0)
    p1_feedback_rate = stats.get("p1_feedback_rate", 0)

    if total == 0:
        return {
            "action": "no_tasks",
            "label": "暂无执行任务",
            "confidence": 0.6,
            "reason": "当前没有可反馈任务。",
        }

    if feedback_rate == 0:
        return {
            "action": "start_feedback_collection",
            "label": "启动执行反馈收集",
            "confidence": 0.75,
            "reason": "已有执行计划，但暂未收到任何反馈，复盘无法判断执行是否落地。",
        }

    if p1_feedback_rate < 0.5:
        return {
            "action": "push_p1_feedback",
            "label": "优先推动 P1 任务反馈",
            "confidence": 0.8,
            "reason": "关键 P1 任务反馈不足，会影响风险处理和复盘准确性。",
        }

    if feedback_rate >= 0.8:
        return {
            "action": "feedback_healthy",
            "label": "执行反馈健康",
            "confidence": 0.85,
            "reason": "多数执行任务已有反馈，可以支持后续复盘和学习。",
        }

    return {
        "action": "continue_collecting_feedback",
        "label": "继续收集执行反馈",
        "confidence": 0.7,
        "reason": "已有部分反馈，但反馈率仍不足，需要继续推动。",
    }


def _build_summary(
    stats: Dict[str, Any],
    decision: Dict[str, Any],
) -> str:
    return (
        f"V12 执行反馈闭环已启动：当前任务 {stats.get('total_tasks', 0)} 项，"
        f"已反馈 {stats.get('done_count', 0)} 项，"
        f"待反馈 {stats.get('pending_count', 0)} 项，"
        f"P1 反馈率 {round(stats.get('p1_feedback_rate', 0) * 100)}%。"
        f"当前建议：{decision.get('label')}。"
    )


def _build_execution(stats: Dict[str, Any]) -> List[str]:
    if stats.get("total_tasks", 0) == 0:
        return [
            "等待 Execution Planner 生成任务。",
        ]

    if stats.get("feedback_rate", 0) == 0:
        return [
            "先在页面上为 V11 执行任务建立反馈入口。",
            "要求组长对今日 P1 任务进行状态确认。",
            "反馈数据不足前，Reflection Engine 不能简单认定策略失败。",
        ]

    return [
        "继续推动未反馈任务。",
        "优先处理 P1 pending 任务。",
        "把 completed / protected / failed 结果提供给 Reflection Engine 复盘。",
    ]
