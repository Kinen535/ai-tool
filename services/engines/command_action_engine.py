from __future__ import annotations

from typing import Any, Dict, List


def build_command_action_report(
    command_report: Dict[str, Any],
    action_key: str,
) -> Dict[str, Any]:
    action_key = str(action_key or "").strip()

    card = _find_card(command_report, action_key)
    playbook = _build_playbook(action_key, command_report)

    return {
        "found": bool(card),
        "action_key": action_key,
        "card": card or _fallback_card(action_key),
        "summary": _build_summary(card, playbook),
        "steps": playbook.get("steps", []),
        "links": playbook.get("links", []),
        "targets": playbook.get("targets", []),
        "checks": playbook.get("checks", []),
        "decision": playbook.get("decision", {}),
        "explain": (
            "V15 Phase B 指挥动作流用于把总控台卡片拆解成可执行步骤。"
            "当前阶段只读引导，不自动修改任务、负责人或学习参数。"
        ),
    }


def _find_card(command_report: Dict[str, Any], action_key: str) -> Dict[str, Any] | None:
    for card in command_report.get("action_cards", []) or []:
        if str(card.get("key") or "") == action_key:
            return card

    return None


def _fallback_card(action_key: str) -> Dict[str, Any]:
    return {
        "key": action_key,
        "level": "info",
        "title": "未知指挥动作",
        "target": action_key,
        "reason": "当前动作不在今日优先处理列表中，可能是状态已经变化。",
        "action": "返回盟务指挥中枢重新查看最新动作。",
        "url": "/command",
    }


def _build_summary(card: Dict[str, Any] | None, playbook: Dict[str, Any]) -> str:
    if not card:
        return "未找到该指挥动作，请返回盟务指挥中枢重新选择。"

    return (
        f"当前指挥动作「{card.get('title')}」已生成执行路线："
        f"目标是 {card.get('target')}。"
        f"建议按步骤处理，并以验收标准确认是否完成。"
    )


def _build_playbook(action_key: str, command_report: Dict[str, Any]) -> Dict[str, Any]:
    if action_key == "fill_leader_owner":
        return _playbook_fill_leader_owner(command_report)

    if action_key == "handle_high_pressure_groups":
        return _playbook_high_pressure(command_report)

    if action_key == "complete_task_feedback":
        return _playbook_task_feedback(command_report)

    if action_key == "review_abnormal_feedback":
        return _playbook_abnormal_feedback(command_report)

    if action_key == "improve_learning_sample":
        return _playbook_learning_sample(command_report)

    if action_key == "routine_patrol":
        return _playbook_routine_patrol(command_report)

    return _playbook_unknown()


def _playbook_fill_leader_owner(command_report: Dict[str, Any]) -> Dict[str, Any]:
    leader_ctx = command_report.get("leader_context", {}) or {}
    high_groups = command_report.get("high_pressure_groups", []) or []

    targets = [
        {
            "name": item.get("group_name"),
            "desc": (
                f"压力 {item.get('pressure_score')}，"
                f"危险 {item.get('danger_count')} / 预警 {item.get('warning_count')}，"
                f"当前负责人：{item.get('leader_display')}"
            ),
            "url": "/leaders?responsibility=unassigned",
        }
        for item in high_groups
        if item.get("responsibility_status") == "unassigned"
    ]

    return {
        "decision": {
            "level": "danger",
            "label": "先补责任链",
            "reason": "没有负责人就无法追责，后续任务反馈和风险处理都会失真。",
        },
        "steps": [
            "进入组长驾驶舱，筛选“待指定组长”。",
            "优先处理高压分组，其次处理成员数多、危险成员多的分组。",
            "给每个分组指定组长、临时负责人或管理代管人。",
            "保存负责人后，检查审计日志是否记录变更。",
            "回到盟务指挥中枢，确认待指定负责人数量下降。",
        ],
        "links": [
            {"label": "查看待指定负责人分组", "url": "/leaders?responsibility=unassigned"},
            {"label": "查看待指定负责人详情", "url": "/leaders/owner/待指定"},
            {"label": "返回盟务指挥中枢", "url": "/command"},
        ],
        "targets": targets[:8],
        "checks": [
            f"待指定负责人分组从 {leader_ctx.get('unassigned_group_count', 0)} 个下降。",
            "高压分组至少都有明确负责人或管理代管人。",
            "负责人映射审计日志出现对应保存记录。",
        ],
    }


def _playbook_high_pressure(command_report: Dict[str, Any]) -> Dict[str, Any]:
    high_groups = command_report.get("high_pressure_groups", []) or []

    targets = [
        {
            "name": item.get("group_name"),
            "desc": (
                f"负责人：{item.get('leader_display')}，"
                f"压力 {item.get('pressure_score')}，"
                f"危险 {item.get('danger_count')} / 预警 {item.get('warning_count')}"
            ),
            "url": "/leaders?pressure=high",
        }
        for item in high_groups
    ]

    return {
        "decision": {
            "level": "warning",
            "label": "按压力排序处理",
            "reason": "高压分组通常是风险成员、任务压力、负责人缺失共同叠加造成。",
        },
        "steps": [
            "先查看高压分组 TOP，确认压力最高的 3 个分组。",
            "点开负责人详情，看该负责人是否同时承担多个高压组。",
            "要求负责人确认风险成员是否真实低活跃、是否应保护或清理。",
            "把处理结果回填到任务反馈或负责人备注中。",
            "下一轮快照后检查压力是否下降。",
        ],
        "links": [
            {"label": "查看高压分组", "url": "/leaders?pressure=high"},
            {"label": "查看任务中心", "url": "/tasks"},
            {"label": "返回盟务指挥中枢", "url": "/command"},
        ],
        "targets": targets[:8],
        "checks": [
            "高压分组负责人明确。",
            "风险成员已有确认、完成、转保护、忽略或失败反馈。",
            "下一轮数据中高压分组数量下降或危险成员减少。",
        ],
    }


def _playbook_task_feedback(command_report: Dict[str, Any]) -> Dict[str, Any]:
    task_ctx = command_report.get("task_context", {}) or {}

    return {
        "decision": {
            "level": "warning",
            "label": "先补 P1 反馈",
            "reason": "任务没有反馈，Reflection 和 Learning 不能稳定判断策略是否有效。",
        },
        "steps": [
            "进入战场任务协同中心。",
            "优先筛选 P1 和待反馈任务。",
            "对已经执行的任务点击确认、完成、转保护、忽略或失败。",
            "对重复提交或状态补充，进入任务详情填写备注。",
            "回到指挥中枢检查待反馈数量和 P1 反馈率。",
        ],
        "links": [
            {"label": "查看待反馈任务", "url": "/tasks?preset=pending"},
            {"label": "查看紧急待反馈", "url": "/tasks?preset=urgent"},
            {"label": "查看任务中心", "url": "/tasks"},
        ],
        "targets": [
            {
                "name": "当前反馈状态",
                "desc": (
                    f"待反馈 {task_ctx.get('pending_count', 0)} 项，"
                    f"P1 反馈率 {task_ctx.get('p1_feedback_rate', 0)}%"
                ),
                "url": "/tasks?preset=pending",
            }
        ],
        "checks": [
            "P1 反馈率明显提升。",
            "待反馈任务数量下降。",
            "Reflection 不再只提示关键任务反馈不足。",
        ],
    }


def _playbook_abnormal_feedback(command_report: Dict[str, Any]) -> Dict[str, Any]:
    task_ctx = command_report.get("task_context", {}) or {}

    return {
        "decision": {
            "level": "info",
            "label": "复核异常原因",
            "reason": "失败、忽略等异常反馈不一定是坏事，但必须有备注说明，否则复盘会误判。",
        },
        "steps": [
            "进入任务中心筛选异常反馈。",
            "点开任务详情页查看反馈历史。",
            "给失败或忽略的任务补充备注，例如联系不上、数据异常、已转保护。",
            "确认是否需要重新执行或改派负责人。",
            "回到指挥中枢查看异常任务是否仍需处理。",
        ],
        "links": [
            {"label": "查看异常反馈", "url": "/tasks?preset=abnormal"},
            {"label": "查看任务中心", "url": "/tasks"},
            {"label": "查看战略中心", "url": "/strategic"},
        ],
        "targets": [
            {
                "name": "异常反馈",
                "desc": f"当前异常任务 {task_ctx.get('abnormal_count', 0)} 项",
                "url": "/tasks?preset=abnormal",
            }
        ],
        "checks": [
            "异常反馈都具备说明备注。",
            "失败任务明确是否需要二次执行。",
            "忽略任务明确是否为合理忽略。",
        ],
    }


def _playbook_learning_sample(command_report: Dict[str, Any]) -> Dict[str, Any]:
    learning_ctx = command_report.get("learning_context", {}) or {}

    return {
        "decision": {
            "level": "info",
            "label": "先补样本再学习",
            "reason": learning_ctx.get("decision_reason") or "当前学习样本质量不足，不适合自动调整参数。",
        },
        "steps": [
            "优先补齐 P1 任务反馈。",
            "确认失败、忽略、转保护都有备注。",
            "等待下一轮快照生成后再看 Reflection。",
            "当有效复盘样本足够后，再考虑 Learning 参数建议。",
        ],
        "links": [
            {"label": "查看任务中心", "url": "/tasks"},
            {"label": "查看战略中心", "url": "/strategic"},
            {"label": "返回盟务指挥中枢", "url": "/command"},
        ],
        "targets": [
            {
                "name": "Learning 状态",
                "desc": learning_ctx.get("summary") or "暂无学习摘要",
                "url": "/strategic",
            }
        ],
        "checks": [
            "P1 反馈率达到可用水平。",
            "有效复盘样本数增加。",
            "Learning 不再被执行反馈质量阻断。",
        ],
    }


def _playbook_routine_patrol(command_report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "decision": {
            "level": "safe",
            "label": "常规巡检",
            "reason": "当前没有明显阻塞，保持巡检即可。",
        },
        "steps": [
            "查看总览和趋势分析是否有新增风险。",
            "检查任务中心是否出现新的 P1 任务。",
            "检查组长驾驶舱是否出现新的高压分组。",
            "等待下一轮快照后复盘变化。",
        ],
        "links": [
            {"label": "查看总览", "url": "/"},
            {"label": "查看趋势分析", "url": "/trends"},
            {"label": "查看组长驾驶舱", "url": "/leaders"},
        ],
        "targets": [],
        "checks": [
            "无新增高压分组。",
            "无大量待反馈任务。",
            "复盘和学习没有新的阻断。",
        ],
    }


def _playbook_unknown() -> Dict[str, Any]:
    return {
        "decision": {
            "level": "info",
            "label": "返回重新选择",
            "reason": "该动作不存在或已经不属于当前优先事项。",
        },
        "steps": [
            "返回盟务指挥中枢。",
            "刷新当前最新状态。",
            "重新选择今日优先处理动作。",
        ],
        "links": [
            {"label": "返回盟务指挥中枢", "url": "/command"},
        ],
        "targets": [],
        "checks": [
            "确认当前动作仍存在。",
        ],
    }
