from __future__ import annotations

from typing import Any, Dict, List


def build_leader_owner_detail_report(
    leader_report: Dict[str, Any],
    owner_name: str,
) -> Dict[str, Any]:
    owner_name = str(owner_name or "").strip()

    groups = [
        item for item in leader_report.get("group_cards", []) or []
        if str(item.get("leader_display") or "").strip() == owner_name
    ]

    stats = _build_stats(groups)
    decision = _build_decision(owner_name, stats, groups)

    return {
        "owner_name": owner_name,
        "found": bool(groups),
        "summary": _build_summary(owner_name, stats, decision),
        "stats": stats,
        "decision": decision,
        "groups": groups,
        "high_groups": [
            item for item in groups
            if item.get("pressure_level") == "high"
        ],
        "pending_groups": [
            item for item in groups
            if item.get("pending_tasks", 0) > 0
        ],
        "abnormal_groups": [
            item for item in groups
            if item.get("abnormal_tasks", 0) > 0
        ],
    }


def _build_stats(groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    task_count = sum(int(g.get("task_count") or 0) for g in groups)
    done_tasks = sum(int(g.get("done_tasks") or 0) for g in groups)

    feedback_rate = 0.0
    if task_count > 0:
        feedback_rate = done_tasks / task_count * 100

    return {
        "group_count": len(groups),
        "member_count": sum(int(g.get("member_count") or 0) for g in groups),
        "high_group_count": len([
            g for g in groups
            if g.get("pressure_level") == "high"
        ]),
        "medium_group_count": len([
            g for g in groups
            if g.get("pressure_level") == "medium"
        ]),
        "danger_count": sum(int(g.get("danger_count") or 0) for g in groups),
        "warning_count": sum(int(g.get("warning_count") or 0) for g in groups),
        "task_count": task_count,
        "pending_tasks": sum(int(g.get("pending_tasks") or 0) for g in groups),
        "done_tasks": done_tasks,
        "abnormal_tasks": sum(int(g.get("abnormal_tasks") or 0) for g in groups),
        "p1_tasks": sum(int(g.get("p1_tasks") or 0) for g in groups),
        "pressure_score": round(sum(float(g.get("pressure_score") or 0) for g in groups), 1),
        "feedback_rate": round(feedback_rate, 1),
    }


def _build_decision(
    owner_name: str,
    stats: Dict[str, Any],
    groups: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not groups:
        return {
            "level": "warning",
            "label": "未找到负责人记录",
            "reason": "当前负责人没有匹配到任何分组，可能是筛选来源或负责人名称变化。",
            "actions": [
                "返回组长驾驶舱检查负责人名称。",
                "必要时重新保存分组负责人映射。",
            ],
        }

    if owner_name == "待指定":
        return {
            "level": "danger",
            "label": "优先补齐负责人",
            "reason": "这些分组尚未指定明确负责人，盟主无法有效追责。",
            "actions": [
                "优先给高压分组指定组长或临时负责人。",
                "对危险人数较多的分组先安排管理层代管。",
                "补齐负责人后再观察下一轮任务反馈。",
            ],
        }

    if stats.get("high_group_count", 0) > 0:
        return {
            "level": "warning",
            "label": "重点约谈负责人",
            "reason": "该负责人名下存在高压分组，需要确认风险复核和任务反馈是否落地。",
            "actions": [
                "先处理压力最高的分组。",
                "要求负责人确认危险成员是否误判。",
                "检查是否存在组内长期低活跃成员。",
            ],
        }

    if stats.get("pending_tasks", 0) > 0:
        return {
            "level": "info",
            "label": "推动补齐反馈",
            "reason": "该负责人名下仍有待反馈任务，会影响后续复盘判断。",
            "actions": [
                "催促负责人补齐待反馈任务。",
                "优先处理 P1 任务。",
            ],
        }

    return {
        "level": "safe",
        "label": "当前可控",
        "reason": "该负责人名下任务反馈较完整，暂无明显高压分组。",
        "actions": [
            "维持常规观察。",
            "等待下一轮快照后复盘变化。",
        ],
    }


def _build_summary(
    owner_name: str,
    stats: Dict[str, Any],
    decision: Dict[str, Any],
) -> str:
    return (
        f"负责人「{owner_name}」当前负责 {stats.get('group_count', 0)} 个分组，"
        f"{stats.get('member_count', 0)} 名成员，"
        f"高压分组 {stats.get('high_group_count', 0)} 个，"
        f"危险成员 {stats.get('danger_count', 0)} 人，"
        f"关联任务 {stats.get('task_count', 0)} 项，"
        f"待反馈 {stats.get('pending_tasks', 0)} 项。"
        f"当前判断：{decision.get('label', '继续观察')}。"
    )
