from __future__ import annotations

from typing import Any, Dict, List


def build_command_center_report(
    staff_report: Dict[str, Any],
    leader_report: Dict[str, Any],
) -> Dict[str, Any]:
    """
    V15 盟务指挥中枢 / 总指挥台

    Phase A：
    - 只读聚合
    - 不写数据库
    - 汇总 V12 任务反馈、V14 组长协同、V11 复盘学习状态
    """

    task_ctx = _extract_task_context(staff_report)
    leader_ctx = _extract_leader_context(leader_report)
    reflection_ctx = _extract_reflection_context(staff_report)
    learning_ctx = _extract_learning_context(staff_report)

    action_cards = _build_action_cards(
        task_ctx,
        leader_ctx,
        reflection_ctx,
        learning_ctx,
    )

    action_cards = _decorate_action_progress(
        action_cards,
        task_ctx,
        leader_ctx,
        learning_ctx,
    )

    action_progress = _build_action_progress_stats(action_cards)

    today_focus = _build_today_focus(
        task_ctx,
        leader_ctx,
        reflection_ctx,
        learning_ctx,
    )

    decision = _build_decision(
        task_ctx,
        leader_ctx,
        reflection_ctx,
        learning_ctx,
    )

    stats = {
        "task_total": task_ctx.get("total_tasks", 0),
        "task_pending": task_ctx.get("pending_count", 0),
        "task_done": task_ctx.get("done_count", 0),
        "p1_feedback_rate": task_ctx.get("p1_feedback_rate", 0),
        "high_pressure_groups": leader_ctx.get("high_pressure_group_count", 0),
        "unassigned_groups": leader_ctx.get("unassigned_group_count", 0),
        "leader_pressure_count": leader_ctx.get("leader_pressure_count", 0),
        "abnormal_tasks": task_ctx.get("abnormal_count", 0),
        "action_total": action_progress.get("total", 0),
        "action_done": action_progress.get("done", 0),
        "action_active": action_progress.get("active", 0),
        "action_blocked": action_progress.get("blocked", 0),
        "action_progress_rate": action_progress.get("progress_rate", 0),
    }

    return {
        "summary": _build_summary(stats, decision),
        "stats": stats,
        "decision": decision,
        "task_context": task_ctx,
        "leader_context": leader_ctx,
        "reflection_context": reflection_ctx,
        "learning_context": learning_ctx,
        "today_focus": today_focus,
        "action_cards": action_cards,
        "action_progress": action_progress,
        "high_pressure_groups": leader_report.get("high_pressure_groups", [])[:8],
        "leader_pressure": leader_report.get("leader_pressure", [])[:8],
        "explain": (
            "V15 Phase A 汇总任务反馈、组长责任、复盘学习等结果，"
            "用于形成盟主每日优先处理顺序。当前阶段只读展示，不自动修改策略。"
        ),
    }


def _extract_task_context(staff_report: Dict[str, Any]) -> Dict[str, Any]:
    fb = staff_report.get("v12_execution_feedback", {}) or {}
    stats = fb.get("stats", {}) or {}

    total = int(stats.get("total_tasks") or 0)
    pending = int(stats.get("pending_count") or 0)
    done = int(stats.get("done_count") or 0)
    abnormal = int(stats.get("abnormal_count") or 0)
    failed = int(stats.get("failed_count") or 0)
    ignored = int(stats.get("ignored_count") or 0)
    p1_total = int(stats.get("p1_total") or 0)
    p1_done = int(stats.get("p1_done") or 0)

    feedback_rate = _safe_percent(done, total)
    p1_feedback_rate = _safe_percent(p1_done, p1_total)

    quality = "normal"

    if p1_total > 0 and p1_feedback_rate < 50:
        quality = "weak_p1_feedback"
    elif pending > 0:
        quality = "has_pending"
    elif abnormal > 0:
        quality = "has_abnormal"
    else:
        quality = "healthy"

    return {
        "total_tasks": total,
        "pending_count": pending,
        "done_count": done,
        "abnormal_count": abnormal,
        "failed_count": failed,
        "ignored_count": ignored,
        "p1_total": p1_total,
        "p1_done": p1_done,
        "feedback_rate": round(feedback_rate, 1),
        "p1_feedback_rate": round(p1_feedback_rate, 1),
        "quality": quality,
        "summary": fb.get("summary") or "",
    }


def _extract_leader_context(leader_report: Dict[str, Any]) -> Dict[str, Any]:
    stats = leader_report.get("stats", {}) or {}

    return {
        "group_count": int(stats.get("group_count") or 0),
        "member_count": int(stats.get("member_count") or 0),
        "high_pressure_group_count": int(stats.get("high_pressure_group_count") or 0),
        "medium_pressure_group_count": int(stats.get("medium_pressure_group_count") or 0),
        "unassigned_group_count": int(stats.get("unassigned_group_count") or 0),
        "manual_mapping_count": int(stats.get("manual_mapping_count") or 0),
        "leader_pressure_count": int(stats.get("leader_pressure_count") or 0),
        "pending_task_count": int(stats.get("pending_task_count") or 0),
        "abnormal_task_count": int(stats.get("abnormal_task_count") or 0),
        "decision": leader_report.get("decision", {}) or {},
        "summary": leader_report.get("summary") or "",
    }


def _extract_reflection_context(staff_report: Dict[str, Any]) -> Dict[str, Any]:
    ref = staff_report.get("v11_reflection_report", {}) or {}
    decision = ref.get("decision", {}) or {}
    execution_feedback = ref.get("execution_feedback", {}) or {}

    return {
        "status": ref.get("status") or "unknown",
        "summary": ref.get("summary") or "",
        "decision_label": decision.get("label") or "",
        "decision_reason": decision.get("reason") or "",
        "feedback_quality": execution_feedback.get("quality") or "",
        "p1_feedback_rate": execution_feedback.get("p1_feedback_rate") or 0,
    }


def _extract_learning_context(staff_report: Dict[str, Any]) -> Dict[str, Any]:
    learning = staff_report.get("v11_learning_report", {}) or {}
    decision = learning.get("decision", {}) or {}

    return {
        "status": learning.get("status") or "unknown",
        "summary": learning.get("summary") or "",
        "decision_label": decision.get("label") or "",
        "decision_reason": decision.get("reason") or "",
    }


def _decorate_action_progress(
    cards: List[Dict[str, Any]],
    task_ctx: Dict[str, Any],
    leader_ctx: Dict[str, Any],
    learning_ctx: Dict[str, Any],
) -> List[Dict[str, Any]]:
    result = []

    for card in cards:
        item = dict(card)
        key = str(item.get("key") or "").strip()

        progress = _build_single_action_progress(
            key,
            task_ctx,
            leader_ctx,
            learning_ctx,
        )

        item.update(progress)
        result.append(item)

    return result


def _build_single_action_progress(
    key: str,
    task_ctx: Dict[str, Any],
    leader_ctx: Dict[str, Any],
    learning_ctx: Dict[str, Any],
) -> Dict[str, Any]:
    if key == "fill_leader_owner":
        remaining = int(leader_ctx.get("unassigned_group_count") or 0)

        if remaining <= 0:
            return _progress_done("负责人已补齐", "当前没有待指定负责人分组。")

        return _progress_active(
            rate=0,
            label="待补负责人",
            reason=f"仍有 {remaining} 个分组缺少明确负责人。",
        )

    if key == "handle_high_pressure_groups":
        remaining = int(leader_ctx.get("high_pressure_group_count") or 0)

        if remaining <= 0:
            return _progress_done("高压分组已清零", "当前没有高压分组。")

        return _progress_active(
            rate=20,
            label="高压处理中",
            reason=f"仍有 {remaining} 个高压分组需要负责人确认。",
        )

    if key == "complete_task_feedback":
        pending = int(task_ctx.get("pending_count") or 0)
        p1_rate = float(task_ctx.get("p1_feedback_rate") or 0)

        if pending <= 0:
            return _progress_done("任务反馈已补齐", "当前没有待反馈任务。")

        if p1_rate < 50:
            return _progress_active(
                rate=round(p1_rate, 1),
                label="P1反馈不足",
                reason=f"P1反馈率 {round(p1_rate, 1)}%，仍需优先补齐关键任务反馈。",
            )

        return _progress_active(
            rate=round(p1_rate, 1),
            label="反馈补齐中",
            reason=f"待反馈 {pending} 项，P1反馈率 {round(p1_rate, 1)}%。",
        )

    if key == "review_abnormal_feedback":
        abnormal = int(task_ctx.get("abnormal_count") or 0)

        if abnormal <= 0:
            return _progress_done("异常已清零", "当前没有异常反馈任务。")

        return _progress_active(
            rate=30,
            label="异常待复核",
            reason=f"仍有 {abnormal} 项失败、忽略或异常反馈需要备注说明。",
        )

    if key == "improve_learning_sample":
        status = str(learning_ctx.get("status") or "").strip()

        if status == "blocked_by_execution_feedback":
            return _progress_blocked(
                label="学习被阻断",
                reason="执行反馈质量不足，Learning 暂不自动调整策略。",
            )

        if status in ("collecting_samples", "no_history"):
            return _progress_active(
                rate=40,
                label="样本积累中",
                reason="Learning 正在等待更多复盘样本。",
            )

        return _progress_done("学习状态正常", "Learning 当前没有明显阻断。")

    if key == "routine_patrol":
        return _progress_done("常规巡检", "当前没有紧急阻断事项。")

    return {
        "progress_status": "unknown",
        "progress_label": "待判断",
        "progress_rate": 0,
        "progress_reason": "当前动作无法识别闭环状态。",
    }


def _build_action_progress_stats(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(cards)

    done = len([
        item for item in cards
        if item.get("progress_status") == "done"
    ])

    active = len([
        item for item in cards
        if item.get("progress_status") == "active"
    ])

    blocked = len([
        item for item in cards
        if item.get("progress_status") == "blocked"
    ])

    if total <= 0:
        progress_rate = 0
    else:
        progress_rate = round(done / total * 100, 1)

    return {
        "total": total,
        "done": done,
        "active": active,
        "blocked": blocked,
        "progress_rate": progress_rate,
    }


def _progress_done(label: str, reason: str) -> Dict[str, Any]:
    return {
        "progress_status": "done",
        "progress_label": label,
        "progress_rate": 100,
        "progress_reason": reason,
    }


def _progress_active(rate: float, label: str, reason: str) -> Dict[str, Any]:
    return {
        "progress_status": "active",
        "progress_label": label,
        "progress_rate": max(0, min(float(rate), 99)),
        "progress_reason": reason,
    }


def _progress_blocked(label: str, reason: str) -> Dict[str, Any]:
    return {
        "progress_status": "blocked",
        "progress_label": label,
        "progress_rate": 0,
        "progress_reason": reason,
    }


def _build_action_cards(
    task_ctx: Dict[str, Any],
    leader_ctx: Dict[str, Any],
    reflection_ctx: Dict[str, Any],
    learning_ctx: Dict[str, Any],
) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []

    if leader_ctx.get("unassigned_group_count", 0) > 0:
        cards.append({
            "key": "fill_leader_owner",
            "level": "danger",
            "title": "补齐分组负责人",
            "target": f"{leader_ctx.get('unassigned_group_count')} 个分组待指定",
            "reason": "分组没有明确负责人，后续任务无法有效追责。",
            "action": "进入组长驾驶舱，优先给高压分组指定负责人。",
            "url": "/leaders?responsibility=unassigned",
        })

    if leader_ctx.get("high_pressure_group_count", 0) > 0:
        cards.append({
            "key": "handle_high_pressure_groups",
            "level": "warning",
            "title": "处理高压分组",
            "target": f"{leader_ctx.get('high_pressure_group_count')} 个高压分组",
            "reason": "部分分组风险成员多、活跃稳定偏低或任务压力较高。",
            "action": "按压力从高到低约谈负责人，确认风险成员与清理候选。",
            "url": "/leaders?pressure=high",
        })

    if task_ctx.get("pending_count", 0) > 0:
        cards.append({
            "key": "complete_task_feedback",
            "level": "warning",
            "title": "补齐任务反馈",
            "target": f"{task_ctx.get('pending_count')} 项待反馈",
            "reason": "执行反馈不足会影响复盘和学习判断。",
            "action": "进入任务协同中心，优先处理 P1 待反馈任务。",
            "url": "/tasks?preset=pending",
        })

    if task_ctx.get("abnormal_count", 0) > 0:
        cards.append({
            "key": "review_abnormal_feedback",
            "level": "info",
            "title": "复核异常反馈",
            "target": f"{task_ctx.get('abnormal_count')} 项异常反馈",
            "reason": "失败、忽略等反馈可能意味着执行受阻或判断有误。",
            "action": "查看任务详情，补充备注并确认是否需要转保护或重新处理。",
            "url": "/tasks?preset=abnormal",
        })

    if learning_ctx.get("status") == "blocked_by_execution_feedback":
        cards.append({
            "key": "improve_learning_sample",
            "level": "info",
            "title": "提升学习样本质量",
            "target": "Learning 暂停自动调整",
            "reason": learning_ctx.get("decision_reason") or "反馈质量不足，暂不适合自动修正策略。",
            "action": "先补齐关键任务反馈，再进入下一轮复盘学习。",
            "url": "/strategic",
        })

    if not cards:
        cards.append({
            "key": "routine_patrol",
            "level": "safe",
            "title": "维持常规巡检",
            "target": "暂无紧急事项",
            "reason": "任务反馈和负责人压力当前可控。",
            "action": "等待下一轮快照后检查风险变化。",
            "url": "/leaders",
        })

    return cards[:8]


def _build_today_focus(
    task_ctx: Dict[str, Any],
    leader_ctx: Dict[str, Any],
    reflection_ctx: Dict[str, Any],
    learning_ctx: Dict[str, Any],
) -> List[str]:
    focus = []

    if leader_ctx.get("unassigned_group_count", 0) > 0:
        focus.append("先补齐待指定负责人，尤其是高压分组。")

    if leader_ctx.get("high_pressure_group_count", 0) > 0:
        focus.append("按高压分组 TOP 顺序点名负责人处理。")

    if task_ctx.get("pending_count", 0) > 0:
        focus.append("补齐 P1 和关键任务反馈，避免复盘失真。")

    if task_ctx.get("abnormal_count", 0) > 0:
        focus.append("复核失败、忽略等异常反馈，确认是否需要重新处理。")

    if learning_ctx.get("status") == "blocked_by_execution_feedback":
        focus.append("Learning 暂不调整策略，先提高执行反馈质量。")

    if not focus:
        focus.append("当前可进入常规观察，等待下一轮快照变化。")

    return focus


def _build_decision(
    task_ctx: Dict[str, Any],
    leader_ctx: Dict[str, Any],
    reflection_ctx: Dict[str, Any],
    learning_ctx: Dict[str, Any],
) -> Dict[str, Any]:
    if leader_ctx.get("unassigned_group_count", 0) > 0:
        return {
            "level": "danger",
            "label": "优先补齐负责人",
            "confidence": 0.86,
            "reason": "当前仍有分组缺少明确负责人，盟主无法形成稳定追责链路。",
        }

    if leader_ctx.get("high_pressure_group_count", 0) > 0:
        return {
            "level": "warning",
            "label": "优先处理高压分组",
            "confidence": 0.84,
            "reason": "当前存在高压分组，需要组长确认风险成员和任务反馈。",
        }

    if task_ctx.get("pending_count", 0) > 0:
        return {
            "level": "warning",
            "label": "优先补齐执行反馈",
            "confidence": 0.8,
            "reason": "当前仍有任务未反馈，会影响复盘和学习准确性。",
        }

    if task_ctx.get("abnormal_count", 0) > 0:
        return {
            "level": "info",
            "label": "复核异常反馈",
            "confidence": 0.75,
            "reason": "当前存在异常反馈，需要确认是否为执行失败或策略误判。",
        }

    return {
        "level": "safe",
        "label": "进入常规巡检",
        "confidence": 0.7,
        "reason": "负责人、任务反馈和复盘状态当前没有明显阻塞。",
    }


def _build_summary(stats: Dict[str, Any], decision: Dict[str, Any]) -> str:
    return (
        f"V15 盟务指挥中枢已启动：当前任务 {stats.get('task_total', 0)} 项，"
        f"待反馈 {stats.get('task_pending', 0)} 项，"
        f"高压分组 {stats.get('high_pressure_groups', 0)} 个，"
        f"待指定负责人分组 {stats.get('unassigned_groups', 0)} 个。"
        f"当前总判断：{decision.get('label', '继续观察')}。"
    )


def _safe_percent(part: int, total: int) -> float:
    if total <= 0:
        return 0.0

    return part / total * 100
