from __future__ import annotations

"""
V11 - Reflection Engine

职责：
1. 对比上一轮 AI 推演与当前实际数据。
2. 输出预测 VS 实际的复盘结果。
3. 不访问数据库。
4. 不调用 LLM。
5. 不修改原始 report。
"""

from typing import Any, Dict, List


def build_reflection_report(report: Dict[str, Any]) -> Dict[str, Any]:
    previous = report.get("previous_v11_snapshot")
    current_sim = report.get("v11_simulation_report", {}) or {}
    current_facts = current_sim.get("facts", {}) or {}

    feedback_report = report.get("v12_execution_feedback", {}) or {}
    feedback_context = _build_feedback_context(feedback_report)

    if not previous:
        return _build_no_history_report(current_facts, feedback_context)

    prev_raw_cleanup = _to_int(previous.get("raw_cleanup_count"))
    curr_raw_cleanup = _to_int(current_facts.get("raw_cleanup_count"))

    prev_shown_cleanup = _to_int(previous.get("shown_cleanup_count"))
    curr_shown_cleanup = _to_int(current_facts.get("shown_cleanup_count"))

    prev_growth = _to_int(previous.get("raw_growth_count"))
    curr_growth = _to_int(current_facts.get("raw_growth_count"))

    expected_risk_reduce = _to_int(previous.get("expected_risk_reduce"))

    actual_risk_reduce = prev_raw_cleanup - curr_raw_cleanup
    risk_delta = curr_raw_cleanup - prev_raw_cleanup
    cleanup_task_delta = curr_shown_cleanup - prev_shown_cleanup
    growth_delta = curr_growth - prev_growth

    status = _judge_status(
        actual_risk_reduce=actual_risk_reduce,
        risk_delta=risk_delta,
        expected_risk_reduce=expected_risk_reduce,
    )

    facts = [
        _fact("previous_raw_cleanup", "上次风险池", prev_raw_cleanup, "上一轮系统识别的原始清理风险数量"),
        _fact("current_raw_cleanup", "当前风险池", curr_raw_cleanup, "当前系统识别的原始清理风险数量"),
        _fact("expected_risk_reduce", "预期风险下降", expected_risk_reduce, "上一轮推演预计能下降的风险数量"),
        _fact("actual_risk_reduce", "实际风险下降", actual_risk_reduce, "两轮数据之间实际下降的风险数量"),
        _fact("risk_delta", "风险变化", risk_delta, "当前风险池相对上一轮的变化"),
        _fact("cleanup_task_delta", "重点清理变化", cleanup_task_delta, "今日重点清理数量相对上一轮的变化"),
        _fact("growth_delta", "培养对象变化", growth_delta, "培养对象数量相对上一轮的变化"),
    ]

    reasoning = _build_reasoning(
        status=status,
        actual_risk_reduce=actual_risk_reduce,
        expected_risk_reduce=expected_risk_reduce,
        risk_delta=risk_delta,
    )

    reasoning.extend(
        _build_feedback_reasoning(
            feedback_context,
            status
        )
    )

    decision = _build_decision(status, actual_risk_reduce, expected_risk_reduce, risk_delta)

    decision = _adjust_decision_by_feedback(
        decision,
        feedback_context,
        status
    )

    return {
        "summary": _build_summary(status, actual_risk_reduce, expected_risk_reduce, risk_delta),
        "status": status,
        "facts": facts,
        "reasoning": reasoning,
        "options": _build_options(),
        "decision": decision,
        "execution": _build_execution(status),
        "review": {
            "next_check": "下一次快照 / 下一次 AI 幕僚中心刷新",
            "success_condition": "风险池继续下降，重点清理对象减少，保护对象无误伤。",
            "failure_condition": "风险池继续扩大，或实际风险下降明显低于预期。",
        },
        "metrics": {
            "previous_raw_cleanup": prev_raw_cleanup,
            "current_raw_cleanup": curr_raw_cleanup,
            "expected_risk_reduce": expected_risk_reduce,
            "actual_risk_reduce": actual_risk_reduce,
            "risk_delta": risk_delta,
            "cleanup_task_delta": cleanup_task_delta,
            "growth_delta": growth_delta,
        },
        "previous_snapshot": {
            "created_at": previous.get("created_at"),
            "selected_scenario": previous.get("selected_scenario"),
            "selected_action": previous.get("selected_action"),
            "confidence": previous.get("confidence"),
        },
        "execution_feedback": feedback_context,
    }


def _build_no_history_report(
    current_facts: Dict[str, Any],
    feedback_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    feedback_context = feedback_context or {}
    facts = [
        _fact("current_raw_cleanup", "当前风险池", current_facts.get("raw_cleanup_count"), "当前系统识别的原始清理风险数量"),
        _fact("current_cleanup_target", "当前重点处理", current_facts.get("shown_cleanup_count"), "当前筛出的重点处理对象"),
        _fact("management_pressure", "管理压力", current_facts.get("management_pressure"), "当前联盟管理压力"),
    ]

    return {
        "summary": "暂无历史推演记录。本次将作为 V11 复盘基线，下一次数据变化后开始进行预测 VS 实际复盘。",
        "status": "no_history",
        "facts": facts,
        "reasoning": [
            {
                "rule": "no_previous_snapshot",
                "logic": "数据库中没有上一轮 V11 推演快照",
                "conclusion": "当前只能建立基线，暂时无法判断预测是否准确。",
            }
        ] + _build_feedback_reasoning(
            feedback_context,
            "no_history"
        ),
        "options": [
            {
                "name": "建立基线",
                "benefit": "为下一次复盘提供对比对象。",
                "risk": "当前无法评价预测准确率。",
            }
        ],
        "decision": {
            "action": "create_baseline",
            "label": "建立 V11 复盘基线",
            "confidence": 0.6,
            "reason": "缺少上一轮预测记录，先保存当前推演结果。",
        },
        "execution": [
            "保存当前 V11 推演结果。",
            "等待下一次快照变化后，再对比预测与实际。",
        ],
        "review": {
            "next_check": "下一次快照",
            "success_condition": "下一轮系统能读取到历史推演记录。",
            "failure_condition": "没有保存历史快照，无法复盘。",
        },
        "metrics": {},
        "previous_snapshot": None,
        "execution_feedback": feedback_context,
    }


def _judge_status(
    actual_risk_reduce: int,
    risk_delta: int,
    expected_risk_reduce: int,
) -> str:
    if expected_risk_reduce <= 0:
        if risk_delta < 0:
            return "improved"
        if risk_delta > 0:
            return "worse"
        return "stable"

    if actual_risk_reduce >= expected_risk_reduce * 0.7:
        return "matched"

    if actual_risk_reduce > 0:
        return "partial"

    if risk_delta > 0:
        return "worse"

    return "stable"


def _build_reasoning(
    status: str,
    actual_risk_reduce: int,
    expected_risk_reduce: int,
    risk_delta: int,
) -> List[Dict[str, Any]]:
    if status == "matched":
        return [
            {
                "rule": "prediction_matched",
                "logic": "实际风险下降达到预期的 70% 以上",
                "conclusion": "上一轮推演基本有效，可以继续沿用当前策略。",
            }
        ]

    if status == "partial":
        return [
            {
                "rule": "prediction_partially_matched",
                "logic": "风险有下降，但低于预期",
                "conclusion": "上一轮策略方向有效，但执行力度或组长反馈可能不足。",
            }
        ]

    if status == "worse":
        return [
            {
                "rule": "prediction_failed",
                "logic": "风险池没有下降，反而扩大",
                "conclusion": "上一轮预测与实际偏差较大，需要提高风险处理强度。",
            }
        ]

    if status == "improved":
        return [
            {
                "rule": "risk_improved_without_expectation",
                "logic": "虽然没有明确预期值，但风险池已经下降",
                "conclusion": "当前执行方向有效。",
            }
        ]

    return [
        {
            "rule": "risk_stable",
            "logic": "风险池变化不明显",
            "conclusion": "当前策略没有明显失败，但也没有产生显著改善。",
        }
    ]


def _build_decision(
    status: str,
    actual_risk_reduce: int,
    expected_risk_reduce: int,
    risk_delta: int,
) -> Dict[str, Any]:
    if status == "matched":
        return {
            "action": "continue_current_strategy",
            "label": "继续当前策略",
            "confidence": 0.85,
            "reason": "实际风险下降基本达到预期。",
        }

    if status == "partial":
        return {
            "action": "continue_but_strengthen_execution",
            "label": "继续策略，但加强执行",
            "confidence": 0.75,
            "reason": "风险有下降，但没有达到预期，需要加强组长确认和执行闭环。",
        }

    if status == "worse":
        return {
            "action": "adjust_strategy",
            "label": "策略需要调整",
            "confidence": 0.8,
            "reason": "风险池扩大，上一轮推演结果没有兑现。",
        }

    return {
        "action": "keep_observing",
        "label": "继续观察",
        "confidence": 0.65,
        "reason": "风险变化不明显，暂不需要大幅调整。",
    }


def _build_summary(
    status: str,
    actual_risk_reduce: int,
    expected_risk_reduce: int,
    risk_delta: int,
) -> str:
    if status == "matched":
        return f"上一轮预测基本兑现：预计风险下降 {expected_risk_reduce}，实际下降 {actual_risk_reduce}。"

    if status == "partial":
        return f"上一轮预测部分兑现：预计风险下降 {expected_risk_reduce}，实际下降 {actual_risk_reduce}，需要加强执行。"

    if status == "worse":
        return f"上一轮预测未兑现：风险池增加 {risk_delta}，需要调整策略。"

    if status == "improved":
        return f"风险池已经下降 {actual_risk_reduce}，当前执行方向有效。"

    return "风险池变化不明显，当前策略需要继续观察。"


def _build_options() -> List[Dict[str, Any]]:
    return [
        {
            "name": "继续当前策略",
            "benefit": "保持策略连续性。",
            "risk": "如果执行不足，风险下降会继续低于预期。",
        },
        {
            "name": "加强执行力度",
            "benefit": "更快降低风险池。",
            "risk": "可能增加组长和管理层压力。",
        },
        {
            "name": "调整策略参数",
            "benefit": "适合预测明显失准时。",
            "risk": "过早调整可能导致规则不稳定。",
        },
    ]


def _build_execution(status: str) -> List[str]:
    if status == "matched":
        return [
            "继续执行当前推荐策略。",
            "保留现有清理阈值和保护复核机制。",
            "下一轮继续观察风险池是否下降。",
        ]

    if status == "partial":
        return [
            "继续执行当前策略，但提高组长反馈要求。",
            "把未反馈对象单独列出，避免任务悬空。",
            "下一轮观察风险下降是否接近预期。",
        ]

    if status == "worse":
        return [
            "复查上一轮清理任务是否真正执行。",
            "检查保护名单是否过宽，导致风险对象未被处理。",
            "必要时提高风险优先级，收紧清理候选规则。",
        ]

    return [
        "继续观察下一轮快照。",
        "保留当前执行链。",
        "等待更明确的数据变化后再调整。",
    ]


def _fact(key: str, label: str, value: Any, meaning: str) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "meaning": meaning,
    }


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0



def _build_feedback_context(feedback_report: Dict[str, Any]) -> Dict[str, Any]:
    stats = feedback_report.get("stats", {}) or {}
    decision = feedback_report.get("decision", {}) or {}

    total_tasks = _to_int(stats.get("total_tasks"))
    done_count = _to_int(stats.get("done_count"))
    pending_count = _to_int(stats.get("pending_count"))
    ignored_count = _to_int(stats.get("ignored_count"))
    failed_count = _to_int(stats.get("failed_count"))

    feedback_rate = _to_float(stats.get("feedback_rate"))
    p1_feedback_rate = _to_float(stats.get("p1_feedback_rate"))

    if total_tasks <= 0:
        quality = "no_tasks"
    elif feedback_rate <= 0:
        quality = "no_feedback"
    elif p1_feedback_rate < 0.5:
        quality = "weak_p1_feedback"
    elif feedback_rate >= 0.8:
        quality = "healthy"
    else:
        quality = "partial_feedback"

    return {
        "total_tasks": total_tasks,
        "done_count": done_count,
        "pending_count": pending_count,
        "ignored_count": ignored_count,
        "failed_count": failed_count,
        "feedback_rate": feedback_rate,
        "p1_feedback_rate": p1_feedback_rate,
        "quality": quality,
        "decision_label": decision.get("label"),
        "decision_reason": decision.get("reason"),
    }


def _build_feedback_reasoning(
    feedback_context: Dict[str, Any],
    reflection_status: str,
) -> List[Dict[str, Any]]:
    quality = feedback_context.get("quality")

    if quality == "no_tasks":
        return [
            {
                "rule": "v12_no_execution_tasks",
                "logic": "当前没有 V12 执行任务反馈对象",
                "conclusion": "复盘只能依据快照变化，无法判断执行落地情况。",
            }
        ]

    if quality == "no_feedback":
        return [
            {
                "rule": "v12_no_feedback",
                "logic": "已有执行任务，但反馈率为 0",
                "conclusion": "如果风险没有下降，不能直接判定策略失败，可能是执行未落地。",
            }
        ]

    if quality == "weak_p1_feedback":
        return [
            {
                "rule": "v12_weak_p1_feedback",
                "logic": "P1 任务反馈率低于 50%",
                "conclusion": "关键任务反馈不足，复盘应优先判断执行问题，而不是马上调整策略。",
            }
        ]

    if quality == "healthy":
        return [
            {
                "rule": "v12_feedback_healthy",
                "logic": "执行反馈率较高，P1 任务反馈充分",
                "conclusion": "当前反馈质量足以支撑策略复盘。",
            }
        ]

    return [
        {
            "rule": "v12_partial_feedback",
            "logic": "已有部分执行反馈，但反馈率尚未充分",
            "conclusion": "复盘可以参考反馈结果，但仍需继续推动未反馈任务。",
        }
    ]


def _adjust_decision_by_feedback(
    decision: Dict[str, Any],
    feedback_context: Dict[str, Any],
    reflection_status: str,
) -> Dict[str, Any]:
    quality = feedback_context.get("quality")

    if quality in ("no_feedback", "weak_p1_feedback"):
        if reflection_status in ("worse", "stable", "partial"):
            return {
                "action": "collect_feedback_before_strategy_change",
                "label": "先补执行反馈，再判断策略",
                "confidence": 0.82,
                "reason": (
                    "当前执行反馈不足，尤其是关键 P1 任务反馈不足。"
                    "在确认任务是否真正执行前，不应直接判定策略失败。"
                ),
            }

    if quality == "healthy" and reflection_status == "worse":
        decision["reason"] = (
            decision.get("reason", "")
            + " 同时 V12 反馈率较高，说明执行信息较充分，策略调整依据更可靠。"
        )

    return decision



def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
