from __future__ import annotations

"""
V12 - Execution Feedback Audit Engine

职责：
1. 分析 V12 执行反馈变更日志。
2. 判断反馈过程是否稳定，是否存在频繁撤回、反复改状态、异常反馈偏多。
3. 不访问数据库。
4. 不调用 LLM。
5. 不修改 report。
"""

from typing import Any, Dict, List


STATUS_LABELS = {
    "pending": "待反馈",
    "confirmed": "已确认",
    "completed": "已完成",
    "protected": "转保护",
    "ignored": "未处理",
    "failed": "执行失败",
}


def build_execution_feedback_audit_report(report: Dict[str, Any]) -> Dict[str, Any]:
    logs = report.get("v12_feedback_logs", []) or []

    stats = _build_audit_stats(logs)
    transition_stats = _build_transition_stats(logs)
    target_stats = _build_target_stats(logs)

    decision = _build_decision(stats)
    summary = _build_summary(stats, decision)

    return {
        "summary": summary,
        "stats": stats,
        "transition_stats": transition_stats,
        "target_stats": target_stats,
        "latest_logs": _format_latest_logs(logs[:20]),
        "decision": decision,
        "execution": _build_execution(stats),
        "review": {
            "next_check": "下一次反馈状态变化后",
            "success_condition": "反馈变更有清晰轨迹，撤回和反复修改数量可控。",
            "failure_condition": "大量任务反复撤回、失败、忽略，导致复盘难以判断执行真实情况。",
        },
    }


def _build_audit_stats(logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_logs = len(logs)

    changed_tasks = len({
        item.get("task_key")
        for item in logs
        if item.get("task_key")
    })

    revert_count = sum(
        1 for item in logs
        if item.get("new_status") == "pending"
    )

    abnormal_count = sum(
        1 for item in logs
        if item.get("new_status") in ("ignored", "failed")
    )

    failed_count = sum(
        1 for item in logs
        if item.get("new_status") == "failed"
    )

    ignored_count = sum(
        1 for item in logs
        if item.get("new_status") == "ignored"
    )

    positive_count = sum(
        1 for item in logs
        if item.get("new_status") in ("confirmed", "completed", "protected")
    )

    return {
        "total_logs": total_logs,
        "changed_tasks": changed_tasks,
        "revert_count": revert_count,
        "abnormal_count": abnormal_count,
        "failed_count": failed_count,
        "ignored_count": ignored_count,
        "positive_count": positive_count,
    }


def _build_transition_stats(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    temp: Dict[str, Dict[str, Any]] = {}

    for item in logs:
        old_status = item.get("old_status") or "pending"
        new_status = item.get("new_status") or "pending"
        key = f"{old_status}->{new_status}"

        if key not in temp:
            temp[key] = {
                "transition": key,
                "old_status": old_status,
                "new_status": new_status,
                "old_label": STATUS_LABELS.get(old_status, old_status),
                "new_label": STATUS_LABELS.get(new_status, new_status),
                "count": 0,
            }

        temp[key]["count"] += 1

    result = list(temp.values())
    result.sort(key=lambda x: x.get("count", 0), reverse=True)

    return result


def _build_target_stats(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    temp: Dict[str, Dict[str, Any]] = {}

    for item in logs:
        target = item.get("target") or "未知对象"

        if target not in temp:
            temp[target] = {
                "target": target,
                "change_count": 0,
                "latest_status": "",
                "latest_time": "",
            }

        temp[target]["change_count"] += 1

        if not temp[target]["latest_time"]:
            temp[target]["latest_status"] = item.get("new_status")
            temp[target]["latest_label"] = STATUS_LABELS.get(
                item.get("new_status"),
                item.get("new_status"),
            )
            temp[target]["latest_time"] = item.get("created_at")

    result = list(temp.values())
    result.sort(key=lambda x: x.get("change_count", 0), reverse=True)

    return result


def _format_latest_logs(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []

    for item in logs:
        old_status = item.get("old_status") or "pending"
        new_status = item.get("new_status") or "pending"

        result.append({
            "created_at": item.get("created_at"),
            "phase": item.get("phase"),
            "priority": item.get("priority"),
            "task_title": item.get("task_title"),
            "target": item.get("target"),
            "owner": item.get("owner"),
            "old_status": old_status,
            "new_status": new_status,
            "old_label": STATUS_LABELS.get(old_status, old_status),
            "new_label": STATUS_LABELS.get(new_status, new_status),
            "feedback_note": item.get("feedback_note", ""),
        })

    return result


def _build_decision(stats: Dict[str, Any]) -> Dict[str, Any]:
    total_logs = stats.get("total_logs", 0)
    revert_count = stats.get("revert_count", 0)
    abnormal_count = stats.get("abnormal_count", 0)

    if total_logs == 0:
        return {
            "action": "no_audit_logs",
            "label": "暂无反馈变更日志",
            "confidence": 0.6,
            "reason": "当前还没有新的反馈状态变化记录。",
        }

    if revert_count >= 3:
        return {
            "action": "review_reverted_feedback",
            "label": "关注频繁撤回",
            "confidence": 0.78,
            "reason": "反馈撤回次数偏多，可能存在误点或执行确认不稳定。",
        }

    if abnormal_count >= 3:
        return {
            "action": "review_abnormal_feedback",
            "label": "关注异常反馈",
            "confidence": 0.8,
            "reason": "忽略或失败反馈较多，需要判断是执行问题还是任务分配问题。",
        }

    return {
        "action": "audit_healthy",
        "label": "反馈轨迹正常",
        "confidence": 0.75,
        "reason": "当前反馈变更有记录，未发现明显异常。",
    }


def _build_summary(
    stats: Dict[str, Any],
    decision: Dict[str, Any],
) -> str:
    return (
        f"V12 反馈审计已启动：累计变更 {stats.get('total_logs', 0)} 次，"
        f"涉及任务 {stats.get('changed_tasks', 0)} 个，"
        f"撤回 {stats.get('revert_count', 0)} 次，"
        f"异常反馈 {stats.get('abnormal_count', 0)} 次。"
        f"当前判断：{decision.get('label')}。"
    )


def _build_execution(stats: Dict[str, Any]) -> List[str]:
    if stats.get("total_logs", 0) == 0:
        return [
            "继续记录后续反馈变化。",
            "等待管理层提交或修改反馈状态。",
        ]

    if stats.get("revert_count", 0) >= 3:
        return [
            "检查是否存在误点或重复修改状态。",
            "对频繁撤回的任务进行人工确认。",
            "必要时增加二次确认弹窗。",
        ]

    if stats.get("abnormal_count", 0) >= 3:
        return [
            "优先查看 ignored / failed 任务。",
            "确认失败原因是任务不合理、组长未执行，还是成员状态特殊。",
            "把异常反馈提供给 Reflection Engine 作为复盘依据。",
        ]

    return [
        "继续保留反馈变更日志。",
        "后续将审计结果接入 Reflection / Learning。",
    ]
