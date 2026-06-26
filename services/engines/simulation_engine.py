from __future__ import annotations

"""
V11 - Simulation Engine

职责：
1. 基于 reasoning_report 做多方案推演。
2. 输出方案 A / B / C 的预计结果。
3. 不访问数据库。
4. 不调用 LLM。
5. 不修改原始 report。
6. staff_engine 只负责调度，本 Engine 负责推演。
"""

from typing import Any, Dict, List


def build_simulation_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    构建 V11 战略推演报告。

    输入：
        report: staff_engine 统一 report

    输出：
        {
            "summary": "...",
            "scenarios": [...],
            "recommended_scenario": {...}
        }
    """

    reasoning = report.get("reasoning_report", {}) or {}
    stats = reasoning.get("reasoning_stats", {}) or {}

    total_members = _to_int(stats.get("total_members_analyzed", 0))
    raw_cleanup_count = _to_int(stats.get("raw_cleanup_count", 0))
    shown_cleanup_count = _to_int(stats.get("shown_cleanup_count", 0))
    shown_protection_count = _to_int(stats.get("shown_protection_count", 0))
    raw_growth_count = _to_int(stats.get("raw_growth_count", 0))

    management_pressure = _estimate_management_pressure(
        total_members=total_members,
        raw_cleanup_count=raw_cleanup_count,
        shown_cleanup_count=shown_cleanup_count,
        shown_protection_count=shown_protection_count,
    )

    scenarios = [
        simulate_risk_first(
            total_members,
            raw_cleanup_count,
            shown_cleanup_count,
            shown_protection_count,
            raw_growth_count,
            management_pressure,
        ),
        simulate_balanced(
            total_members,
            raw_cleanup_count,
            shown_cleanup_count,
            shown_protection_count,
            raw_growth_count,
            management_pressure,
        ),
        simulate_growth_first(
            total_members,
            raw_cleanup_count,
            shown_cleanup_count,
            shown_protection_count,
            raw_growth_count,
            management_pressure,
        ),
    ]

    scenarios.sort(
        key=lambda item: item.get("score", 0),
        reverse=True,
    )

    recommended = scenarios[0] if scenarios else {}

    return {
        "summary": build_simulation_summary(recommended, scenarios),
        "scenarios": scenarios,
        "recommended_scenario": recommended,
        "facts": {
            "total_members": total_members,
            "raw_cleanup_count": raw_cleanup_count,
            "shown_cleanup_count": shown_cleanup_count,
            "shown_protection_count": shown_protection_count,
            "raw_growth_count": raw_growth_count,
            "management_pressure": management_pressure,
        },
    }


def simulate_risk_first(
    total_members: int,
    raw_cleanup_count: int,
    shown_cleanup_count: int,
    shown_protection_count: int,
    raw_growth_count: int,
    management_pressure: str,
) -> Dict[str, Any]:
    """
    方案 A：风险优先。
    适合风险成员较多、管理压力较高时。
    """

    expected_risk_reduce = min(shown_cleanup_count, 20)
    expected_management_cost = shown_cleanup_count + shown_protection_count
    expected_stability_gain = expected_risk_reduce * 1.8
    expected_growth_loss = 0 if raw_growth_count == 0 else min(raw_growth_count, 5) * 0.5

    score = (
        expected_stability_gain
        - expected_growth_loss
        - expected_management_cost * 0.15
    )

    return {
        "scenario_id": "A",
        "name": "风险优先",
        "decision_type": "simulation",
        "score": round(score, 2),
        "facts": [
            _fact("total_members", "成员总数", total_members, "当前被推演的成员规模"),
            _fact("raw_cleanup_count", "原始清理风险", raw_cleanup_count, "系统识别出的潜在清理风险规模"),
            _fact("shown_cleanup_count", "今日重点清理", shown_cleanup_count, "今日建议优先处理的清理候选"),
            _fact("shown_protection_count", "保护复核", shown_protection_count, "需要避免误伤的保护复核对象"),
            _fact("management_pressure", "管理压力", management_pressure, "当前联盟管理压力等级"),
        ],
        "reasoning": [
            {
                "rule": "risk_first_when_high_pressure",
                "logic": "原始清理风险较高，且今日重点清理对象已经筛出",
                "conclusion": "当前更适合先降低主盟风险，而不是优先扩张培养。",
            },
            {
                "rule": "cleanup_with_protection_review",
                "logic": "清理候选与保护复核同时存在",
                "conclusion": "执行清理前必须保留人工确认，避免误伤战略成员。",
            },
        ],
        "options": [
            {
                "name": "当天集中处理 20 名重点清理候选",
                "benefit": "快速释放低贡献成员占位，降低管理负担。",
                "risk": "如果组长确认不到位，可能误伤短期有事成员。",
            },
            {
                "name": "先处理 TOP10，再处理剩余对象",
                "benefit": "节奏更稳，降低组长压力。",
                "risk": "风险下降速度较慢。",
            },
            {
                "name": "暂缓清理，仅做观察",
                "benefit": "不会误伤成员。",
                "risk": "低贡献成员继续占位，风险继续累积。",
            },
        ],
        "decision": {
            "action": "risk_first",
            "label": "方案 A：风险优先",
            "confidence": _confidence_from_pressure(management_pressure, base=0.78),
            "reason": "当前清理风险池较大，应优先降低联盟不稳定因素。",
        },
        "expected_result": {
            "risk_reduce": expected_risk_reduce,
            "management_cost": expected_management_cost,
            "stability_gain": round(expected_stability_gain, 1),
            "growth_loss": round(expected_growth_loss, 1),
            "overall_effect": "风险下降快，培养节奏暂缓。",
        },
        "execution": [
            "优先通知相关组长确认 TOP20 清理候选状态。",
            "保护复核成员不得直接清理，必须确认身份和战略用途。",
            "24小时内无回应的普通低贡献成员进入清理名单。",
            "清理完成后重新观察下一次快照风险数量变化。",
        ],
        "review": {
            "next_check": "下一次快照",
            "success_condition": "原始清理风险数量下降，今日重点清理对象减少。",
            "failure_condition": "清理后风险数量没有下降，或保护对象被误伤。",
        },
    }


def simulate_balanced(
    total_members: int,
    raw_cleanup_count: int,
    shown_cleanup_count: int,
    shown_protection_count: int,
    raw_growth_count: int,
    management_pressure: str,
) -> Dict[str, Any]:
    """
    方案 B：风险与培养平衡。
    适合风险存在，但仍希望保留发展节奏时。
    """

    cleanup_target = min(shown_cleanup_count, 10)
    growth_target = min(raw_growth_count, 5)

    expected_risk_reduce = cleanup_target
    expected_growth_gain = growth_target * 1.5
    expected_management_cost = cleanup_target + shown_protection_count + growth_target

    score = (
        expected_risk_reduce * 1.2
        + expected_growth_gain
        - expected_management_cost * 0.12
    )

    return {
        "scenario_id": "B",
        "name": "风险与培养平衡",
        "decision_type": "simulation",
        "score": round(score, 2),
        "facts": [
            _fact("total_members", "成员总数", total_members, "当前被推演的成员规模"),
            _fact("cleanup_target", "清理处理目标", cleanup_target, "该方案下计划处理的清理候选数量"),
            _fact("growth_target", "培养处理目标", growth_target, "该方案下计划培养的成员数量"),
            _fact("shown_protection_count", "保护复核", shown_protection_count, "需要避免误伤的保护复核对象"),
            _fact("management_pressure", "管理压力", management_pressure, "当前联盟管理压力等级"),
        ],
        "reasoning": [
            {
                "rule": "balanced_when_growth_exists",
                "logic": "同时处理风险与培养对象",
                "conclusion": "该方案能在降低风险的同时保留骨干建设节奏。",
            },
            {
                "rule": "limited_cleanup_to_reduce_cost",
                "logic": "清理对象限制在 TOP10",
                "conclusion": "减少组长当天处理压力，适合稳健执行。",
            },
        ],
        "options": [
            {
                "name": "处理 TOP10 风险成员，同时跟进培养对象",
                "benefit": "风险下降和人才建设同步推进。",
                "risk": "管理层执行压力中等。",
            },
            {
                "name": "风险处理和培养分两天执行",
                "benefit": "节奏更稳。",
                "risk": "战场变化快时可能错过处理窗口。",
            },
            {
                "name": "只做风险处理，不做培养",
                "benefit": "执行简单。",
                "risk": "容易忽略潜力成员。",
            },
        ],
        "decision": {
            "action": "balanced_management",
            "label": "方案 B：风险与培养平衡",
            "confidence": 0.72,
            "reason": "该方案适合管理资源充足、希望稳步推进的情况。",
        },
        "expected_result": {
            "risk_reduce": expected_risk_reduce,
            "management_cost": expected_management_cost,
            "growth_gain": round(expected_growth_gain, 1),
            "overall_effect": "风险适度下降，培养节奏保留。",
        },
        "execution": [
            "先处理 TOP10 高风险清理候选。",
            "同时安排组长跟进保护复核对象。",
            "若存在培养候选，则分配明确任务验证成长性。",
            "下一次快照同时观察风险下降和成长恢复。",
        ],
        "review": {
            "next_check": "下一次快照",
            "success_condition": "风险成员减少，同时培养对象保持上升趋势。",
            "failure_condition": "风险未下降，且培养对象没有产生新增贡献。",
        },
    }


def simulate_growth_first(
    total_members: int,
    raw_cleanup_count: int,
    shown_cleanup_count: int,
    shown_protection_count: int,
    raw_growth_count: int,
    management_pressure: str,
) -> Dict[str, Any]:
    """
    方案 C：培养优先。
    适合风险较低、成长对象较多时。
    """

    growth_target = min(raw_growth_count, 10)
    delayed_risk = shown_cleanup_count

    expected_growth_gain = growth_target * 2.0
    expected_risk_delay_cost = delayed_risk * 0.8
    expected_management_cost = growth_target + shown_protection_count

    score = (
        expected_growth_gain
        - expected_risk_delay_cost
        - expected_management_cost * 0.1
    )

    return {
        "scenario_id": "C",
        "name": "培养优先",
        "decision_type": "simulation",
        "score": round(score, 2),
        "facts": [
            _fact("total_members", "成员总数", total_members, "当前被推演的成员规模"),
            _fact("raw_growth_count", "潜在培养对象", raw_growth_count, "系统识别出的成长对象规模"),
            _fact("delayed_risk", "暂缓风险对象", delayed_risk, "该方案下被延后处理的风险对象"),
            _fact("management_pressure", "管理压力", management_pressure, "当前联盟管理压力等级"),
        ],
        "reasoning": [
            {
                "rule": "growth_first_requires_low_risk",
                "logic": "只有当风险较低且培养对象明显时，才适合培养优先",
                "conclusion": "当前若风险池较大，培养优先会放大管理隐患。",
            },
            {
                "rule": "delayed_cleanup_cost",
                "logic": "清理对象被延后处理",
                "conclusion": "短期内低贡献成员会继续占用主盟位置。",
            },
        ],
        "options": [
            {
                "name": "优先培养成长对象",
                "benefit": "有利于长期骨干建设。",
                "risk": "风险成员继续占位，纪律压力增加。",
            },
            {
                "name": "只培养最强 TOP3",
                "benefit": "管理成本较低。",
                "risk": "对整体风险改善有限。",
            },
            {
                "name": "暂缓培养，先处理风险",
                "benefit": "先稳住主盟基本盘。",
                "risk": "可能错过成长窗口。",
            },
        ],
        "decision": {
            "action": "growth_first",
            "label": "方案 C：培养优先",
            "confidence": _confidence_growth_first(raw_cleanup_count, raw_growth_count),
            "reason": "该方案只有在风险压力较低、成长对象较多时才适合。",
        },
        "expected_result": {
            "growth_gain": round(expected_growth_gain, 1),
            "risk_delay_cost": round(expected_risk_delay_cost, 1),
            "management_cost": expected_management_cost,
            "overall_effect": "成长收益依赖培养对象数量，风险处理会被延后。",
        },
        "execution": [
            "筛选成长对象并安排明确战场任务。",
            "暂缓低优先级清理对象。",
            "保留对高风险成员的最低限度监控。",
            "下一次快照判断成长收益是否抵消风险延后成本。",
        ],
        "review": {
            "next_check": "下一次快照",
            "success_condition": "培养对象继续上升，且风险没有明显扩大。",
            "failure_condition": "培养收益不明显，同时风险成员继续增加。",
        },
    }


def build_simulation_summary(
    recommended: Dict[str, Any],
    scenarios: List[Dict[str, Any]],
) -> str:
    if not recommended:
        return "当前数据不足，暂时无法生成战略推演。"

    name = recommended.get("name", "未知方案")
    reason = recommended.get("decision", {}).get("reason", "")

    return f"当前推荐执行「{name}」。{reason}"


def _estimate_management_pressure(
    total_members: int,
    raw_cleanup_count: int,
    shown_cleanup_count: int,
    shown_protection_count: int,
) -> str:
    if total_members <= 0:
        return "未知"

    risk_ratio = raw_cleanup_count / total_members

    if risk_ratio >= 0.35 or shown_cleanup_count >= 20:
        return "高"

    if risk_ratio >= 0.18 or shown_cleanup_count >= 10:
        return "中"

    if shown_protection_count >= 5:
        return "中"

    return "低"


def _confidence_from_pressure(pressure: str, base: float = 0.7) -> float:
    if pressure == "高":
        return round(min(base + 0.12, 0.95), 2)

    if pressure == "中":
        return round(min(base + 0.05, 0.9), 2)

    if pressure == "低":
        return round(max(base - 0.08, 0.55), 2)

    return round(base, 2)


def _confidence_growth_first(raw_cleanup_count: int, raw_growth_count: int) -> float:
    if raw_growth_count <= 0:
        return 0.35

    if raw_cleanup_count > raw_growth_count * 3:
        return 0.45

    if raw_growth_count >= raw_cleanup_count:
        return 0.78

    return 0.62


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
