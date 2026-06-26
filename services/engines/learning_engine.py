from __future__ import annotations

"""
V11/V12 - Learning Engine

职责：
1. 读取 Reflection Engine 的复盘结果与历史复盘记录。
2. 统计预测误差、识别策略稳定性、给出学习建议。
3. 接入 V12 执行反馈质量，避免把“执行未落地”误学成“策略失败”。
4. 当前阶段只做安全学习骨架：
   - 不自动修改权重
   - 不自动修改参数
   - 不自动覆盖策略
5. 不访问数据库。
6. 不调用 LLM。
"""

from typing import Any, Dict, List


MIN_VALID_REFLECTIONS = 3


def build_learning_report(report: Dict[str, Any]) -> Dict[str, Any]:
    reflection = report.get("v11_reflection_report", {}) or {}
    history = report.get("v11_reflection_history", []) or []

    execution_feedback = _extract_execution_feedback_context(
        report,
        reflection,
    )

    valid_history = [
        item for item in history
        if item.get("status") not in ("no_history", None, "")
    ]

    current_status = reflection.get("status", "unknown")

    metrics = _build_learning_metrics(
        valid_history,
        reflection,
    )

    signals = _build_learning_signals(
        valid_history,
        reflection,
        metrics,
        execution_feedback,
    )

    suggestions = _build_parameter_suggestions(
        metrics,
        current_status,
        execution_feedback,
    )

    learning_status = _judge_learning_status(
        valid_history,
        metrics,
        current_status,
        execution_feedback,
    )

    return {
        "summary": _build_summary(
            learning_status,
            len(valid_history),
            current_status,
            execution_feedback,
        ),
        "status": learning_status,
        "safe_mode": True,
        "auto_apply": False,
        "history_count": len(history),
        "valid_reflection_count": len(valid_history),
        "current_reflection_status": current_status,
        "metrics": metrics,
        "execution_feedback": execution_feedback,
        "learning_signals": signals,
        "parameter_suggestions": suggestions,
        "decision": _build_decision(
            learning_status,
            current_status,
            len(valid_history),
            execution_feedback,
        ),
        "execution": _build_execution(
            learning_status,
            execution_feedback,
        ),
        "review": {
            "next_check": "下一次 V11/V12 复盘完成后",
            "success_condition": "累计足够复盘样本，并且执行反馈质量足够支撑学习判断。",
            "failure_condition": "复盘样本不足、执行反馈不足、数据长期不变化，或误差方向反复震荡。",
        },
    }


def _extract_execution_feedback_context(
    report: Dict[str, Any],
    reflection: Dict[str, Any],
) -> Dict[str, Any]:
    """
    优先读取 Reflection Engine 已整理好的 execution_feedback。
    如果没有，则回退读取 v12_execution_feedback.stats。
    """
    ref_feedback = reflection.get("execution_feedback", {}) or {}

    if ref_feedback:
        return {
            "total_tasks": _to_int(ref_feedback.get("total_tasks")),
            "done_count": _to_int(ref_feedback.get("done_count")),
            "pending_count": _to_int(ref_feedback.get("pending_count")),
            "ignored_count": _to_int(ref_feedback.get("ignored_count")),
            "failed_count": _to_int(ref_feedback.get("failed_count")),
            "feedback_rate": _to_float(ref_feedback.get("feedback_rate")),
            "p1_feedback_rate": _to_float(ref_feedback.get("p1_feedback_rate")),
            "quality": ref_feedback.get("quality") or "unknown",
            "decision_label": ref_feedback.get("decision_label") or "",
            "decision_reason": ref_feedback.get("decision_reason") or "",
        }

    fb = report.get("v12_execution_feedback", {}) or {}
    stats = fb.get("stats", {}) or {}
    decision = fb.get("decision", {}) or {}

    total_tasks = _to_int(stats.get("total_tasks"))
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
        "done_count": _to_int(stats.get("done_count")),
        "pending_count": _to_int(stats.get("pending_count")),
        "ignored_count": _to_int(stats.get("ignored_count")),
        "failed_count": _to_int(stats.get("failed_count")),
        "feedback_rate": feedback_rate,
        "p1_feedback_rate": p1_feedback_rate,
        "quality": quality,
        "decision_label": decision.get("label") or "",
        "decision_reason": decision.get("reason") or "",
    }


def _build_learning_metrics(
    valid_history: List[Dict[str, Any]],
    current_reflection: Dict[str, Any],
) -> Dict[str, Any]:
    matched = _count_status(valid_history, "matched")
    partial = _count_status(valid_history, "partial")
    worse = _count_status(valid_history, "worse")
    stable = _count_status(valid_history, "stable")
    improved = _count_status(valid_history, "improved")

    error_values = []

    for item in valid_history:
        expected = _to_float(item.get("expected_risk_reduce"))
        actual = _to_float(item.get("actual_risk_reduce"))

        if expected > 0:
            error_values.append(abs(expected - actual))

    avg_abs_error = round(sum(error_values) / len(error_values), 2) if error_values else 0

    current_metrics = current_reflection.get("metrics", {}) or {}
    current_expected = _to_float(current_metrics.get("expected_risk_reduce"))
    current_actual = _to_float(current_metrics.get("actual_risk_reduce"))

    current_error = 0

    if current_expected > 0:
        current_error = round(abs(current_expected - current_actual), 2)

    total_valid = len(valid_history)

    return {
        "matched_count": matched,
        "partial_count": partial,
        "worse_count": worse,
        "stable_count": stable,
        "improved_count": improved,
        "valid_count": total_valid,
        "avg_abs_error": avg_abs_error,
        "current_expected_risk_reduce": current_expected,
        "current_actual_risk_reduce": current_actual,
        "current_abs_error": current_error,
        "matched_ratio": round(matched / total_valid, 2) if total_valid else 0,
        "worse_ratio": round(worse / total_valid, 2) if total_valid else 0,
    }


def _build_learning_signals(
    valid_history: List[Dict[str, Any]],
    current_reflection: Dict[str, Any],
    metrics: Dict[str, Any],
    execution_feedback: Dict[str, Any],
) -> List[Dict[str, Any]]:
    signals = []

    feedback_quality = execution_feedback.get("quality")

    if feedback_quality in ("no_feedback", "weak_p1_feedback"):
        signals.append({
            "level": "warning",
            "name": "执行反馈不足",
            "conclusion": "关键任务反馈不足，Learning Engine 不应把当前结果直接学习为策略失败。",
            "evidence": (
                f"feedback_rate={execution_feedback.get('feedback_rate')}, "
                f"p1_feedback_rate={execution_feedback.get('p1_feedback_rate')}"
            ),
        })

    elif feedback_quality == "healthy":
        signals.append({
            "level": "positive",
            "name": "执行反馈健康",
            "conclusion": "当前执行反馈质量较高，后续复盘结果更适合作为学习样本。",
            "evidence": (
                f"feedback_rate={execution_feedback.get('feedback_rate')}, "
                f"p1_feedback_rate={execution_feedback.get('p1_feedback_rate')}"
            ),
        })

    elif feedback_quality == "partial_feedback":
        signals.append({
            "level": "info",
            "name": "部分执行反馈",
            "conclusion": "已有部分任务反馈，但样本仍不充分，学习结论需要保守。",
            "evidence": (
                f"feedback_rate={execution_feedback.get('feedback_rate')}, "
                f"p1_feedback_rate={execution_feedback.get('p1_feedback_rate')}"
            ),
        })

    if len(valid_history) < MIN_VALID_REFLECTIONS:
        signals.append({
            "level": "info",
            "name": "复盘样本不足",
            "conclusion": "当前有效复盘样本不足，Learning Engine 只能记录误差，不能给出稳定参数修正。",
            "evidence": f"有效复盘样本 {len(valid_history)} / {MIN_VALID_REFLECTIONS}",
        })
        return signals

    if metrics.get("matched_ratio", 0) >= 0.6:
        signals.append({
            "level": "positive",
            "name": "策略稳定",
            "conclusion": "近期预测兑现率较高，当前推演规则暂时不需要调整。",
            "evidence": f"matched_ratio={metrics.get('matched_ratio')}",
        })

    if metrics.get("worse_ratio", 0) >= 0.4:
        if feedback_quality in ("healthy", "partial_feedback"):
            signals.append({
                "level": "warning",
                "name": "预测失准偏高",
                "conclusion": "在执行反馈相对充分的情况下，预测失准比例偏高，需要人工检查风险阈值和执行闭环。",
                "evidence": f"worse_ratio={metrics.get('worse_ratio')}",
            })
        else:
            signals.append({
                "level": "warning",
                "name": "失准但反馈不足",
                "conclusion": "虽然预测失准比例偏高，但执行反馈不足，不能直接修改策略参数。",
                "evidence": f"worse_ratio={metrics.get('worse_ratio')}, feedback_quality={feedback_quality}",
            })

    if metrics.get("avg_abs_error", 0) >= 10:
        signals.append({
            "level": "warning",
            "name": "平均误差偏高",
            "conclusion": "预期风险下降与实际风险下降差距较大，后续应降低预测乐观程度。",
            "evidence": f"avg_abs_error={metrics.get('avg_abs_error')}",
        })

    if not signals:
        signals.append({
            "level": "neutral",
            "name": "继续观察",
            "conclusion": "当前未发现强烈学习信号，建议继续积累复盘样本。",
            "evidence": "没有触发稳定、失准、高误差或反馈不足规则。",
        })

    return signals


def _build_parameter_suggestions(
    metrics: Dict[str, Any],
    current_status: str,
    execution_feedback: Dict[str, Any],
) -> List[Dict[str, Any]]:
    suggestions = []

    feedback_quality = execution_feedback.get("quality")

    if feedback_quality in ("no_feedback", "weak_p1_feedback"):
        suggestions.append({
            "parameter": "learning_guardrail",
            "current": "安全学习",
            "suggested": "先提高 P1 任务反馈率，再判断是否需要调整策略参数",
            "auto_apply": False,
            "reason": "关键执行反馈不足，当前不能区分策略问题和执行问题。",
        })

    if current_status == "matched":
        suggestions.append({
            "parameter": "risk_first_strategy",
            "current": "保持",
            "suggested": "继续沿用",
            "auto_apply": False,
            "reason": "当前预测基本兑现，不建议调整核心策略。",
        })

    elif current_status == "partial":
        suggestions.append({
            "parameter": "execution_intensity",
            "current": "正常",
            "suggested": "人工提高组长反馈要求",
            "auto_apply": False,
            "reason": "方向有效但执行不足，应先加强执行，而不是改动模型参数。",
        })

    elif current_status == "worse":
        if feedback_quality == "healthy":
            suggestions.append({
                "parameter": "risk_threshold_review",
                "current": "现有阈值",
                "suggested": "人工复核清理阈值、保护名单规则、风险优先级",
                "auto_apply": False,
                "reason": "执行反馈较充分但风险恶化，具备人工复核策略参数的条件。",
            })
        else:
            suggestions.append({
                "parameter": "execution_feedback_first",
                "current": "反馈不足",
                "suggested": "先补齐关键任务反馈，再复核策略参数",
                "auto_apply": False,
                "reason": "风险恶化可能来自执行未落地，不能直接修改策略参数。",
            })

    else:
        suggestions.append({
            "parameter": "learning_mode",
            "current": "观察",
            "suggested": "继续积累复盘记录与执行反馈",
            "auto_apply": False,
            "reason": "当前没有足够证据支持参数调整。",
        })

    if metrics.get("avg_abs_error", 0) >= 10 and feedback_quality == "healthy":
        suggestions.append({
            "parameter": "expected_risk_reduce_factor",
            "current": "当前预测系数",
            "suggested": "未来可考虑降低预期风险下降估算",
            "auto_apply": False,
            "reason": "历史平均误差偏高，且执行反馈质量较高，但当前阶段仍只记录建议。",
        })

    return suggestions


def _judge_learning_status(
    valid_history: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    current_status: str,
    execution_feedback: Dict[str, Any],
) -> str:
    feedback_quality = execution_feedback.get("quality")

    if feedback_quality in ("no_feedback", "weak_p1_feedback"):
        return "blocked_by_execution_feedback"

    if len(valid_history) < MIN_VALID_REFLECTIONS:
        return "collecting_samples"

    if metrics.get("worse_ratio", 0) >= 0.4:
        return "needs_review"

    if metrics.get("matched_ratio", 0) >= 0.6:
        return "stable"

    if metrics.get("avg_abs_error", 0) >= 10:
        return "high_error"

    return "watching"


def _build_summary(
    learning_status: str,
    valid_count: int,
    current_status: str,
    execution_feedback: Dict[str, Any],
) -> str:
    if learning_status == "blocked_by_execution_feedback":
        return (
            "Learning Engine 已接入 V12 执行反馈：当前关键任务反馈不足，"
            "系统不会把当前结果直接学习为策略失败，需先提高 P1 反馈率。"
        )

    if learning_status == "collecting_samples":
        return (
            f"Learning Engine 已启动安全模式：当前有效复盘样本 {valid_count} 条，"
            "暂不自动修正权重，只记录误差、执行反馈与学习信号。"
        )

    if learning_status == "stable":
        return "近期预测兑现率较高，且执行反馈质量足够，当前策略暂时稳定。"

    if learning_status == "needs_review":
        return "近期预测失准比例偏高，且执行反馈具备参考价值，需要人工复核策略参数。"

    if learning_status == "high_error":
        return "近期预测误差偏高，建议降低推演预期或复查执行落地情况。"

    return "当前学习信号不强，建议继续观察并积累更多复盘与执行反馈样本。"


def _build_decision(
    learning_status: str,
    current_status: str,
    valid_count: int,
    execution_feedback: Dict[str, Any],
) -> Dict[str, Any]:
    if learning_status == "blocked_by_execution_feedback":
        return {
            "action": "improve_execution_feedback_first",
            "label": "先提高执行反馈质量",
            "confidence": 0.82,
            "reason": "P1 任务反馈不足，Learning Engine 暂不判断策略参数是否需要调整。",
        }

    if learning_status == "collecting_samples":
        return {
            "action": "collect_more_samples",
            "label": "继续收集复盘样本",
            "confidence": 0.7,
            "reason": "有效复盘样本不足，不能贸然调整权重或参数。",
        }

    if learning_status == "stable":
        return {
            "action": "keep_strategy",
            "label": "维持当前策略参数",
            "confidence": 0.8,
            "reason": "历史复盘显示预测兑现率较高。",
        }

    if learning_status == "needs_review":
        return {
            "action": "manual_review_required",
            "label": "需要人工复核策略参数",
            "confidence": 0.78,
            "reason": "预测失准比例偏高，且执行反馈具备一定参考价值。",
        }

    if learning_status == "high_error":
        return {
            "action": "reduce_prediction_confidence",
            "label": "降低预测乐观程度",
            "confidence": 0.75,
            "reason": "历史平均误差偏高，后续推演应更保守。",
        }

    return {
        "action": "keep_observing",
        "label": "继续观察学习信号",
        "confidence": 0.65,
        "reason": "当前没有足够强的学习信号。",
    }


def _build_execution(
    learning_status: str,
    execution_feedback: Dict[str, Any],
) -> List[str]:
    if learning_status == "blocked_by_execution_feedback":
        return [
            "优先推动 P1 任务反馈，尤其是风险清理和保护复核任务。",
            "把 ignored / failed 与 pending 区分开，避免误判组长无反馈。",
            "反馈质量不足前，不自动调整权重、阈值或策略参数。",
        ]

    if learning_status == "collecting_samples":
        return [
            "继续保存每轮 V11 推演快照。",
            "继续保存每轮 Reflection Engine 复盘结果。",
            "继续保存 V12 执行反馈结果。",
            "至少积累 3 条有效复盘记录后，再评估是否需要调整参数。",
        ]

    if learning_status == "stable":
        return [
            "保持当前风险优先策略。",
            "继续观察预测兑现率是否稳定。",
            "暂不调整权重。",
        ]

    if learning_status == "needs_review":
        return [
            "人工检查风险池扩大的原因。",
            "复核保护名单是否过宽。",
            "检查清理任务是否真正执行。",
            "暂不自动修改阈值。",
        ]

    if learning_status == "high_error":
        return [
            "记录高误差情况。",
            "后续推演中降低预期风险下降估算。",
            "等待更多复盘样本确认误差方向。",
        ]

    return [
        "继续观察下一轮复盘结果。",
        "暂不调整参数。",
    ]


def _count_status(items: List[Dict[str, Any]], status: str) -> int:
    return sum(1 for item in items if item.get("status") == status)


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
