from __future__ import annotations

"""
V11 - LLM Layer

职责：
1. 负责解释，不负责决策。
2. 当前阶段不调用真实大模型，只生成规则模板解释。
3. 未来可接 GPT / DeepSeek / Qwen / Gemini / 豆包。
4. 不访问数据库。
5. 不修改 report。
6. 所有核心决策仍来自 Rule Engine。
"""

from typing import Any, Dict, List


def build_llm_explanation_report(report: Dict[str, Any]) -> Dict[str, Any]:
    reasoning = report.get("reasoning_report", {}) or {}
    simulation = report.get("v11_simulation_report", {}) or {}
    execution = report.get("v11_execution_plan", {}) or {}
    reflection = report.get("v11_reflection_report", {}) or {}
    learning = report.get("v11_learning_report", {}) or {}

    recommended = simulation.get("recommended_scenario", {}) or {}
    recommended_decision = recommended.get("decision", {}) or {}

    explanation_sections = [
        _build_overview_section(reasoning, simulation, execution),
        _build_reasoning_section(reasoning),
        _build_simulation_section(simulation),
        _build_execution_section(execution),
        _build_reflection_section(reflection),
        _build_learning_section(learning),
    ]

    return {
        "enabled": True,
        "provider": "rule_template",
        "llm_api_enabled": False,
        "decision_source": "Rule Engine",
        "explanation_source": "V11 LLM Layer Template",
        "summary": _build_summary(recommended, reflection, learning),
        "sections": explanation_sections,
        "final_message": _build_final_message(recommended, execution, reflection, learning),
        "safety_rules": [
            "LLM Layer 只解释，不参与核心决策。",
            "所有清理、保护、培养、推演、执行与学习建议均来自规则引擎。",
            "未来接入真实大模型时，只允许读取结构化 report 并生成自然语言说明。",
            "禁止大模型直接修改权重、阈值、成员名单或执行计划。",
        ],
    }


def _build_overview_section(
    reasoning: Dict[str, Any],
    simulation: Dict[str, Any],
    execution: Dict[str, Any],
) -> Dict[str, Any]:
    sim_facts = simulation.get("facts", {}) or {}
    recommended = simulation.get("recommended_scenario", {}) or {}

    return {
        "title": "一、当前局势总览",
        "level": "overview",
        "content": (
            f"当前系统共分析 {sim_facts.get('total_members', 0)} 名成员，"
            f"识别出原始风险池 {sim_facts.get('raw_cleanup_count', 0)} 人，"
            f"今日重点处理 {sim_facts.get('shown_cleanup_count', 0)} 人，"
            f"管理压力为「{sim_facts.get('management_pressure', '未知')}」。"
            f"综合推演后，系统推荐执行「{recommended.get('name', '未知方案')}」。"
        ),
        "source": "simulation_report.facts + recommended_scenario",
    }


def _build_reasoning_section(reasoning: Dict[str, Any]) -> Dict[str, Any]:
    stats = reasoning.get("reasoning_stats", {}) or {}

    return {
        "title": "二、为什么这样判断",
        "level": "reasoning",
        "content": (
            f"Reasoning Engine 先从全部成员中筛出重点对象，"
            f"不是把所有风险都直接交给盟主处理。"
            f"本轮原始清理风险为 {stats.get('raw_cleanup_count', 0)} 人，"
            f"但只展示今日最需要处理的 {stats.get('shown_cleanup_count', 0)} 人，"
            f"同时保留 {stats.get('shown_protection_count', 0)} 名保护复核对象，"
            f"避免误伤管理号、战略号、门神号或高价值成员。"
        ),
        "source": "reasoning_report.reasoning_stats",
    }


def _build_simulation_section(simulation: Dict[str, Any]) -> Dict[str, Any]:
    scenarios = simulation.get("scenarios", []) or []
    recommended = simulation.get("recommended_scenario", {}) or {}

    scenario_text = []

    for item in scenarios:
        scenario_text.append(
            f"方案 {item.get('scenario_id')}「{item.get('name')}」评分 {item.get('score')}，"
            f"可信度 {round((item.get('decision', {}).get('confidence', 0) or 0) * 100)}%。"
        )

    return {
        "title": "三、方案推演结果",
        "level": "simulation",
        "content": (
            "系统对不同战略方案进行了规则推演："
            + " ".join(scenario_text)
            + f" 最终推荐「{recommended.get('name', '未知方案')}」，"
            + f"原因是：{recommended.get('decision', {}).get('reason', '暂无原因')}。"
        ),
        "source": "v11_simulation_report.scenarios",
    }


def _build_execution_section(execution: Dict[str, Any]) -> Dict[str, Any]:
    phases = execution.get("phases", {}) or {}

    today_count = len(phases.get("today", []) or [])
    tomorrow_count = len(phases.get("tomorrow", []) or [])
    week_count = len(phases.get("this_week", []) or [])
    season_count = len(phases.get("season", []) or [])

    return {
        "title": "四、接下来怎么执行",
        "level": "execution",
        "content": (
            f"Execution Planner 已经把推荐方案拆成执行链："
            f"今天 {today_count} 项，明天 {tomorrow_count} 项，"
            f"本周 {week_count} 项，赛季 {season_count} 项。"
            f"当前重点不是继续讨论策略，而是推动组长确认清理候选状态、"
            f"复核保护对象，并在下一轮快照中验证风险池是否下降。"
        ),
        "source": "v11_execution_plan.phases",
    }


def _build_reflection_section(reflection: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": "五、如何复盘",
        "level": "reflection",
        "content": (
            f"Reflection Engine 当前状态为「{reflection.get('status', '未知')}」。"
            f"{reflection.get('summary', '')}"
            f"下一轮系统会把本轮预测与实际风险变化进行对比，判断预测是否兑现。"
        ),
        "source": "v11_reflection_report",
    }


def _build_learning_section(learning: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": "六、系统如何学习",
        "level": "learning",
        "content": (
            f"Learning Engine 当前状态为「{learning.get('status', '未知')}」，"
            f"有效复盘样本 {learning.get('valid_reflection_count', 0)} 条。"
            f"系统当前处于安全学习模式，只记录误差和学习信号，"
            f"不会自动修改权重、参数或策略。"
        ),
        "source": "v11_learning_report",
    }


def _build_summary(
    recommended: Dict[str, Any],
    reflection: Dict[str, Any],
    learning: Dict[str, Any],
) -> str:
    scenario_name = recommended.get("name", "未知方案")
    reflection_status = reflection.get("status", "未知")
    learning_status = learning.get("status", "未知")

    return (
        f"LLM Layer 已生成解释：当前推荐方案为「{scenario_name}」，"
        f"复盘状态为「{reflection_status}」，学习状态为「{learning_status}」。"
        "本解释只用于表达和辅助理解，不参与核心决策。"
    )


def _build_final_message(
    recommended: Dict[str, Any],
    execution: Dict[str, Any],
    reflection: Dict[str, Any],
    learning: Dict[str, Any],
) -> str:
    scenario_name = recommended.get("name", "未知方案")
    decision_reason = recommended.get("decision", {}).get("reason", "")

    return (
        f"当前最稳妥的管理动作是执行「{scenario_name}」。"
        f"{decision_reason}"
        "短期重点应放在清理候选确认、保护对象复核和下一轮快照复盘。"
        "在有效复盘样本不足前，系统不会自动调整权重。"
    )
