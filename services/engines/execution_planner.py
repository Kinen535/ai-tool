from __future__ import annotations

"""
V11 - Execution Planner

职责：
1. 基于 Reasoning Engine 与 Simulation Engine 的结果生成执行链。
2. 输出：今天、明天、本周、赛季级执行计划。
3. 不访问数据库。
4. 不调用 LLM。
5. 不修改原始 report。
6. staff_engine 只负责调度，本 Engine 负责执行规划。
"""

from typing import Any, Dict, List


def build_execution_plan_report(report: Dict[str, Any]) -> Dict[str, Any]:
    reasoning = report.get("reasoning_report", {}) or {}
    simulation = report.get("v11_simulation_report", {}) or {}

    recommended = simulation.get("recommended_scenario", {}) or {}
    action = recommended.get("decision", {}).get("action", "")
    scenario_name = recommended.get("name", "未知方案")

    member_reasoning = reasoning.get("member_reasoning", []) or []

    cleanup_items = _filter_items(member_reasoning, "cleanup")
    protection_items = _filter_items(member_reasoning, "protection")
    growth_items = _filter_items(member_reasoning, "growth")

    if action == "risk_first":
        phases = _build_risk_first_plan(
            cleanup_items,
            protection_items,
            growth_items,
            recommended,
        )
    elif action == "balanced_management":
        phases = _build_balanced_plan(
            cleanup_items,
            protection_items,
            growth_items,
            recommended,
        )
    elif action == "growth_first":
        phases = _build_growth_first_plan(
            cleanup_items,
            protection_items,
            growth_items,
            recommended,
        )
    else:
        phases = _build_default_plan(
            cleanup_items,
            protection_items,
            growth_items,
            recommended,
        )

    return {
        "summary": _build_summary(scenario_name, phases),
        "selected_scenario": scenario_name,
        "selected_action": action,
        "facts": {
            "cleanup_count": len(cleanup_items),
            "protection_count": len(protection_items),
            "growth_count": len(growth_items),
            "scenario_score": recommended.get("score"),
            "confidence": recommended.get("decision", {}).get("confidence"),
        },
        "phases": phases,
        "decision_chain": {
            "facts": _build_plan_facts(cleanup_items, protection_items, growth_items, recommended),
            "reasoning": _build_plan_reasoning(action, recommended),
            "options": _build_plan_options(),
            "decision": {
                "action": action or "manual_review",
                "label": f"执行推荐方案：{scenario_name}",
                "confidence": recommended.get("decision", {}).get("confidence", 0.6),
                "reason": recommended.get("decision", {}).get("reason", "当前缺少推荐方案，需要人工复核。"),
            },
            "execution": _flatten_phase_tasks(phases),
            "review": {
                "next_check": "下一次快照 / 明日 AI 幕僚中心",
                "success_condition": "风险对象减少，保护对象无误伤，执行任务有明确反馈。",
                "failure_condition": "风险数量未下降、组长无反馈、保护成员被误清或低贡献继续扩大。",
            },
        },
    }


def _build_risk_first_plan(
    cleanup_items: List[Dict[str, Any]],
    protection_items: List[Dict[str, Any]],
    growth_items: List[Dict[str, Any]],
    recommended: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    today = []

    for item in cleanup_items[:10]:
        today.append(_task(
            phase="today",
            priority="P1",
            title="确认清理候选状态",
            target=item.get("target_name"),
            owner="所属组长",
            action="确认是否请假、铺路、门神、器械号或战略保护号；无有效原因则列入清理名单。",
            reason=item.get("decision", {}).get("reason", ""),
            deadline="今天内",
            review_metric="是否完成状态确认",
        ))

    for item in protection_items[:5]:
        today.append(_task(
            phase="today",
            priority="P1",
            title="保护对象复核",
            target=item.get("target_name"),
            owner="管理层 / 组长",
            action="确认保护原因是否仍然有效，避免被普通清理规则误伤。",
            reason=item.get("decision", {}).get("reason", ""),
            deadline="今天内",
            review_metric="是否明确保护原因",
        ))

    tomorrow = [
        _task(
            phase="tomorrow",
            priority="P1",
            title="执行无回应成员清理",
            target="今日未反馈的清理候选",
            owner="盟主 / 管理层",
            action="对 24 小时内无回应且无战略用途的成员执行清理。",
            reason="风险优先方案要求快速降低主盟不稳定因素。",
            deadline="明天",
            review_metric="清理名单是否完成",
        ),
        _task(
            phase="tomorrow",
            priority="P2",
            title="复查保护对象",
            target="保护复核名单",
            owner="管理层",
            action="对仍未说明用途的保护对象进行二次确认，必要时降级观察。",
            reason="保护机制不能变成长期占位。",
            deadline="明天",
            review_metric="保护对象是否完成分类",
        ),
    ]

    this_week = [
        _task(
            phase="this_week",
            priority="P2",
            title="建立风险成员处理节奏",
            target="风险中心 / 各分组",
            owner="管理层",
            action="每轮快照后固定筛出 TOP20 风险对象，由组长确认后处理。",
            reason="避免风险池长期堆积。",
            deadline="本周",
            review_metric="raw_cleanup_count 是否下降",
        ),
        _task(
            phase="this_week",
            priority="P2",
            title="补充主盟有效成员",
            target="主盟空位",
            owner="招募 / 管理层",
            action="清理后优先补入稳定活跃成员或战略小号。",
            reason="清理不是目的，提升主盟有效战斗力才是目的。",
            deadline="本周",
            review_metric="主盟有效人数是否恢复",
        ),
    ]

    season = [
        _task(
            phase="season",
            priority="P3",
            title="沉淀保护名单制度",
            target="身份中心",
            owner="管理层",
            action="明确门神号、器械号、铺路号、管理号、战略号的保护规则。",
            reason="降低后续误清风险。",
            deadline="赛季内",
            review_metric="保护对象是否都有明确原因",
        ),
        _task(
            phase="season",
            priority="P3",
            title="建立组长责任制",
            target="所有分组",
            owner="盟主 / 管理层",
            action="每个分组固定由组长确认低活跃成员状态，超过期限自动进入清理流程。",
            reason="把 AI 判断转化为可执行管理流程。",
            deadline="赛季内",
            review_metric="组长反馈率",
        ),
    ]

    return {
        "today": today,
        "tomorrow": tomorrow,
        "this_week": this_week,
        "season": season,
    }


def _build_balanced_plan(
    cleanup_items: List[Dict[str, Any]],
    protection_items: List[Dict[str, Any]],
    growth_items: List[Dict[str, Any]],
    recommended: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    today = []

    for item in cleanup_items[:5]:
        today.append(_task(
            phase="today",
            priority="P1",
            title="处理 TOP5 高风险成员",
            target=item.get("target_name"),
            owner="所属组长",
            action="先确认状态，再决定清理或观察。",
            reason=item.get("decision", {}).get("reason", ""),
            deadline="今天内",
            review_metric="状态是否确认",
        ))

    for item in growth_items[:5]:
        today.append(_task(
            phase="today",
            priority="P2",
            title="培养对象沟通",
            target=item.get("target_name"),
            owner="组长",
            action="确认成员意愿，并安排明确战场任务。",
            reason=item.get("decision", {}).get("reason", ""),
            deadline="今天内",
            review_metric="是否接受任务",
        ))

    tomorrow = [
        _task(
            phase="tomorrow",
            priority="P1",
            title="执行确认后的风险处理",
            target="TOP5 风险成员",
            owner="管理层",
            action="对已确认无有效原因的成员清理，对有原因的成员转观察。",
            reason="平衡方案强调稳健执行。",
            deadline="明天",
            review_metric="处理结果是否闭环",
        )
    ]

    this_week = [
        _task(
            phase="this_week",
            priority="P2",
            title="风险与培养双线跟踪",
            target="风险成员 + 培养成员",
            owner="管理层",
            action="每次快照同时观察风险下降和成长贡献。",
            reason="保持联盟纪律与长期成长。",
            deadline="本周",
            review_metric="风险下降且成长对象有新增贡献",
        )
    ]

    season = [
        _task(
            phase="season",
            priority="P3",
            title="建立骨干培养池",
            target="人才中心",
            owner="管理层",
            action="把稳定上升成员纳入长期培养池。",
            reason="平衡方案不能只处理风险，也要积累骨干。",
            deadline="赛季内",
            review_metric="培养池成员留存和贡献变化",
        )
    ]

    return {
        "today": today,
        "tomorrow": tomorrow,
        "this_week": this_week,
        "season": season,
    }


def _build_growth_first_plan(
    cleanup_items: List[Dict[str, Any]],
    protection_items: List[Dict[str, Any]],
    growth_items: List[Dict[str, Any]],
    recommended: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    today = []

    for item in growth_items[:10]:
        today.append(_task(
            phase="today",
            priority="P1",
            title="重点培养对象派发任务",
            target=item.get("target_name"),
            owner="组长",
            action="安排战场任务、协作任务或资源任务，验证成长性。",
            reason=item.get("decision", {}).get("reason", ""),
            deadline="今天内",
            review_metric="是否完成任务反馈",
        ))

    tomorrow = [
        _task(
            phase="tomorrow",
            priority="P2",
            title="最低限度风险监控",
            target="高风险成员",
            owner="管理层",
            action="只处理最严重的风险对象，其余暂缓。",
            reason="培养优先会延后风险处理，必须保留底线监控。",
            deadline="明天",
            review_metric="风险是否扩大",
        )
    ]

    this_week = [
        _task(
            phase="this_week",
            priority="P2",
            title="验证培养收益",
            target="培养对象",
            owner="管理层",
            action="检查培养对象是否带来战功、助攻、捐献或势力增长。",
            reason="培养优先必须用实际贡献证明收益。",
            deadline="本周",
            review_metric="培养对象贡献增量",
        )
    ]

    season = [
        _task(
            phase="season",
            priority="P3",
            title="形成核心梯队",
            target="人才中心",
            owner="管理层",
            action="把高成长成员转入骨干、组长候选或战场核心梯队。",
            reason="培养优先的最终目标是形成长期组织资产。",
            deadline="赛季内",
            review_metric="核心梯队人数与稳定度",
        )
    ]

    return {
        "today": today,
        "tomorrow": tomorrow,
        "this_week": this_week,
        "season": season,
    }


def _build_default_plan(
    cleanup_items: List[Dict[str, Any]],
    protection_items: List[Dict[str, Any]],
    growth_items: List[Dict[str, Any]],
    recommended: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "today": [
            _task(
                phase="today",
                priority="P1",
                title="人工复核 AI 推演结果",
                target="AI 幕僚中心",
                owner="盟主 / 管理层",
                action="当前推荐方案不明确，先由盟主确认推演结果是否合理。",
                reason="缺少明确推荐方案。",
                deadline="今天内",
                review_metric="是否完成方案确认",
            )
        ],
        "tomorrow": [],
        "this_week": [],
        "season": [],
    }


def _filter_items(items: List[Dict[str, Any]], decision_type: str) -> List[Dict[str, Any]]:
    return [
        item for item in items
        if item.get("decision_type") == decision_type
    ]


def _task(
    phase: str,
    priority: str,
    title: str,
    target: str,
    owner: str,
    action: str,
    reason: str,
    deadline: str,
    review_metric: str,
) -> Dict[str, Any]:
    return {
        "phase": phase,
        "priority": priority,
        "title": title,
        "target": target or "未指定",
        "owner": owner,
        "action": action,
        "reason": reason,
        "deadline": deadline,
        "review_metric": review_metric,
    }


def _build_summary(scenario_name: str, phases: Dict[str, List[Dict[str, Any]]]) -> str:
    today_count = len(phases.get("today", []))
    tomorrow_count = len(phases.get("tomorrow", []))
    week_count = len(phases.get("this_week", []))
    season_count = len(phases.get("season", []))

    return (
        f"当前基于「{scenario_name}」生成执行链："
        f"今天 {today_count} 项，明天 {tomorrow_count} 项，"
        f"本周 {week_count} 项，赛季 {season_count} 项。"
    )


def _build_plan_facts(
    cleanup_items: List[Dict[str, Any]],
    protection_items: List[Dict[str, Any]],
    growth_items: List[Dict[str, Any]],
    recommended: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [
        _fact("scenario", "推荐方案", recommended.get("name"), "Simulation Engine 选择的推荐方案"),
        _fact("cleanup_items", "清理任务数", len(cleanup_items), "当前可转化为执行任务的清理推理对象"),
        _fact("protection_items", "保护复核数", len(protection_items), "需要避免误伤的保护对象"),
        _fact("growth_items", "培养任务数", len(growth_items), "当前可转化为培养任务的对象"),
    ]


def _build_plan_reasoning(action: str, recommended: Dict[str, Any]) -> List[Dict[str, Any]]:
    if action == "risk_first":
        return [
            {
                "rule": "risk_first_execution",
                "logic": "Simulation Engine 推荐风险优先",
                "conclusion": "执行计划应优先围绕清理确认、保护复核和风险下降设计。",
            }
        ]

    if action == "balanced_management":
        return [
            {
                "rule": "balanced_execution",
                "logic": "Simulation Engine 推荐风险与培养平衡",
                "conclusion": "执行计划应同时处理高风险成员和培养对象。",
            }
        ]

    if action == "growth_first":
        return [
            {
                "rule": "growth_first_execution",
                "logic": "Simulation Engine 推荐培养优先",
                "conclusion": "执行计划应优先围绕成长对象任务派发和贡献验证设计。",
            }
        ]

    return [
        {
            "rule": "manual_review_required",
            "logic": "缺少明确推荐方案",
            "conclusion": "执行计划应先进入人工复核。",
        }
    ]


def _build_plan_options() -> List[Dict[str, Any]]:
    return [
        {
            "name": "按推荐方案执行",
            "benefit": "与推演结果保持一致，执行链最清晰。",
            "risk": "如果原始数据异常，可能放大错误判断。",
        },
        {
            "name": "只执行今日任务",
            "benefit": "风险较低，方便先验证效果。",
            "risk": "无法形成完整管理闭环。",
        },
        {
            "name": "人工调整后执行",
            "benefit": "适合存在特殊战场背景时。",
            "risk": "会降低系统自动化程度。",
        },
    ]


def _flatten_phase_tasks(phases: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    result: List[str] = []

    phase_labels = {
        "today": "今天",
        "tomorrow": "明天",
        "this_week": "本周",
        "season": "赛季",
    }

    for phase_key in ["today", "tomorrow", "this_week", "season"]:
        label = phase_labels.get(phase_key, phase_key)
        for task in phases.get(phase_key, []):
            result.append(
                f"{label}｜{task.get('priority')}｜{task.get('title')}｜{task.get('target')}"
            )

    return result


def _fact(key: str, label: str, value: Any, meaning: str) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "meaning": meaning,
    }
