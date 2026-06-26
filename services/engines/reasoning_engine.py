from __future__ import annotations

"""
V11 - Reasoning Engine

职责：
1. 生成 AI 决策推理链。
2. 输出：事实 → 推理 → 多方案 → 决策 → 执行 → 复盘。
3. 不访问数据库。
4. 不调用 LLM。
5. 不修改原始 report。
6. staff_engine 只负责调度，本 Engine 负责推理。
"""

from typing import Any, Dict, List, Optional


LOW_AV = 30
LOW_BS = 40
MID_AV = 50
MID_BS = 60
HIGH_AV = 70
HIGH_BS = 70
HIGH_IDENTITY = 65
HIGH_WAR_VALUE = 60


def build_reasoning_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    构建 V11 推理报告。

    输入：
        report: staff_engine 组装后的统一 report

    输出：
        {
            "member_reasoning": [...],
            "group_reasoning": [...],
            "alliance_reasoning": [...],
            "summary": "..."
        }
    """
    members = _collect_members_from_report(report)

    cleanup_reasoning: List[Dict[str, Any]] = []
    protection_reasoning: List[Dict[str, Any]] = []
    growth_reasoning: List[Dict[str, Any]] = []

    for member in members:
        protect_result = reason_member_protection(member)
        cleanup_result = reason_member_cleanup(member)
        growth_result = reason_member_growth(member)

        # 保护优先级高于清理，避免误伤管理层、核心号、门神号、战略号
        if protect_result:
            protection_reasoning.append(protect_result)
            continue

        if cleanup_result:
            cleanup_reasoning.append(cleanup_result)
            continue

        if growth_result:
            growth_reasoning.append(growth_result)

    cleanup_reasoning.sort(key=_reasoning_priority, reverse=True)
    protection_reasoning.sort(key=_reasoning_priority, reverse=True)
    growth_reasoning.sort(key=_reasoning_priority, reverse=True)

    # V11 的推理输出必须可执行，不能把风险中心重复一遍。
    # 因此这里只输出重点推理对象，原始数量放入 reasoning_stats。
    member_reasoning = (
        cleanup_reasoning[:20]
        + protection_reasoning[:10]
        + growth_reasoning[:10]
    )

    group_reasoning = reason_groups(report)
    alliance_reasoning = reason_alliance(report)

    reasoning_stats = {
        "total_members_analyzed": len(members),
        "raw_cleanup_count": len(cleanup_reasoning),
        "raw_protection_count": len(protection_reasoning),
        "raw_growth_count": len(growth_reasoning),
        "shown_cleanup_count": min(len(cleanup_reasoning), 20),
        "shown_protection_count": min(len(protection_reasoning), 10),
        "shown_growth_count": min(len(growth_reasoning), 10),
    }

    return {
        "member_reasoning": member_reasoning,
        "group_reasoning": group_reasoning,
        "alliance_reasoning": alliance_reasoning,
        "reasoning_stats": reasoning_stats,
        "summary": build_reasoning_summary(
            member_reasoning,
            group_reasoning,
            alliance_reasoning,
        ),
    }


def reason_member_cleanup(member: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    成员清理推理。

    注意：
    这里只输出“清理候选”或“跟进建议”，不直接执行清理。
    """
    name = _member_name(member)
    if not name:
        return None

    av = _to_float(_get(member, "av", "active_value", "activity"))
    bs = _to_float(_get(member, "bs", "stability_value", "stability"))
    trend = _get(member, "trend", default="")
    risk_level = _get(member, "risk_level", "risk", default="")
    risk_reason = _get(member, "risk_reason", default="")
    stall_count = _to_int(_get(member, "stall_count", default=0))
    health = _to_float(_get(member, "health", "health_score", default=None))

    hit_low_score = av is not None and bs is not None and av < LOW_AV and bs < LOW_BS
    hit_health = health is not None and health < 30

    # 长期停滞要结合低活跃，避免把战略号、门神号、特殊任务号直接推入清理。
    hit_stall = (
        stall_count >= 5
        and (av is None or av < 40)
    )

    hit_danger = risk_level in ("danger", "clear")

    # danger 不能单独等于清理候选。
    # 必须同时存在低活跃、低稳定、下滑、停滞等可解释事实。
    hit_danger_with_evidence = (
        hit_danger
        and (
            (av is not None and av < 40)
            or (bs is not None and bs < 45)
            or trend in ("down", "dead")
            or stall_count >= 3
        )
    )

    if not (
        hit_low_score
        or hit_health
        or hit_stall
        or hit_danger_with_evidence
    ):
        return None

    facts = _base_member_facts(member)
    reasoning = []

    if hit_low_score:
        reasoning.append({
            "rule": "low_activity_and_low_stability",
            "logic": f"活跃度 < {LOW_AV} 且 稳定度 < {LOW_BS}",
            "conclusion": "该成员近期贡献不足，并且状态不是短期波动。",
        })

    if hit_health:
        reasoning.append({
            "rule": "low_health_score",
            "logic": "健康度 < 30",
            "conclusion": "综合状态已经进入高风险区间。",
        })

    if hit_stall:
        reasoning.append({
            "rule": "continuous_stall",
            "logic": "连续停滞期数 >= 5",
            "conclusion": "该成员长期没有明显增长，需要进入重点处理名单。",
        })

    if hit_danger:
        reasoning.append({
            "rule": "danger_risk_level",
            "logic": "风险等级为 danger / clear",
            "conclusion": "系统已将该成员识别为高风险对象。",
        })

    if trend in ("down", "dead"):
        reasoning.append({
            "rule": "negative_trend",
            "logic": "趋势为 down / dead",
            "conclusion": "该成员状态仍在下滑，继续观察的收益较低。",
        })

    return {
        "target_type": "member",
        "target_name": name,
        "decision_type": "cleanup",
        "facts": facts,
        "reasoning": reasoning,
        "options": [
            {
                "name": "立即清理",
                "benefit": "快速释放主盟名额，降低低贡献成员占位。",
                "risk": "可能误伤短期有事但仍愿意回归的成员。",
            },
            {
                "name": "组长最后跟进一次",
                "benefit": "降低误判风险，保留人工确认环节。",
                "risk": "如果执行拖延，会继续占用管理资源。",
            },
            {
                "name": "暂缓处理，继续观察",
                "benefit": "适合存在特殊身份或特殊任务的成员。",
                "risk": "若没有特殊原因，容易造成清理标准失效。",
            },
        ],
        "decision": {
            "action": "group_follow_up_before_cleanup",
            "label": "清理候选：建议组长最后确认",
            "confidence": _confidence_cleanup(member),
            "reason": risk_reason or "活跃度、稳定度或趋势已触发高风险规则。",
        },
        "execution": [
            "通知所属组长确认该成员是否请假、铺路、门神、器械号或战略保护号。",
            "若 24 小时内无有效回应，列入清理名单。",
            "若确认有战略用途，转入保护名单并标注原因。",
        ],
        "review": {
            "next_check": "下一次快照",
            "success_condition": "成员活跃度、稳定度或贡献增量明显恢复。",
            "failure_condition": "继续停滞、继续下滑或无任何有效回应。",
        },
    }


def reason_member_protection(member: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    成员保护推理。

    用于避免误伤：
    - 管理层
    - 组长
    - 高身份评分成员
    - 高战争价值成员
    - 已标记保护成员
    """
    name = _member_name(member)
    if not name:
        return None

    is_protected = _to_int(_get(member, "is_protected", default=0)) == 1
    role_tag = _get(member, "role_tag", default="")
    identity_score = _to_float(_get(member, "identity_score", default=0)) or 0
    wv = _to_float(_get(member, "wv", "war_value", default=0)) or 0
    risk_level = _get(member, "risk_level", "risk", default="")
    trend = _get(member, "trend", default="")
    av = _to_float(_get(member, "av", "active_value", "activity", default=None))
    bs = _to_float(_get(member, "bs", "stability_value", "stability", default=None))
    stall_count = _to_int(_get(member, "stall_count", default=0))

    protected_role = role_tag in ("admin", "leader", "core", "protected")
    high_identity = identity_score >= HIGH_IDENTITY
    high_war_value = wv >= HIGH_WAR_VALUE

    # 保护推理不是“身份展示”，而是“风险下的误伤保护”。
    # 只有成员已经出现风险压力时，高身份、高战争价值、保护标记才进入保护复核。
    risk_pressure = (
        risk_level in ("danger", "clear")
        or (av is not None and bs is not None and av < LOW_AV and bs < LOW_BS)
        or trend in ("down", "dead")
        or stall_count >= 5
    )

    has_protection_value = (
        is_protected
        or protected_role
        or high_identity
        or high_war_value
    )

    if not (risk_pressure and has_protection_value):
        return None

    facts = _base_member_facts(member)
    reasoning = []

    if is_protected:
        reasoning.append({
            "rule": "manual_protection",
            "logic": "is_protected = 1",
            "conclusion": "该成员已经被系统或人工标记为保护对象。",
        })

    if protected_role:
        reasoning.append({
            "rule": "protected_role",
            "logic": "成员身份属于管理层、组长、核心或保护对象",
            "conclusion": "该成员具有组织或战略身份，不应直接按普通成员规则处理。",
        })

    if high_identity:
        reasoning.append({
            "rule": "high_identity_score",
            "logic": f"身份评分 >= {HIGH_IDENTITY}",
            "conclusion": "该成员历史价值或组织价值较高，需要谨慎处理。",
        })

    if high_war_value:
        reasoning.append({
            "rule": "high_war_value",
            "logic": f"战争价值 >= {HIGH_WAR_VALUE}",
            "conclusion": "该成员具备较高战场价值，不建议直接清理。",
        })

    if risk_level in ("danger", "clear"):
        reasoning.append({
            "rule": "risk_but_protected",
            "logic": "风险较高，但同时命中保护规则",
            "conclusion": "该成员应从清理逻辑转入人工复核或战略保护逻辑。",
        })

    return {
        "target_type": "member",
        "target_name": name,
        "decision_type": "protection",
        "facts": facts,
        "reasoning": reasoning,
        "options": [
            {
                "name": "继续保护",
                "benefit": "避免误伤核心成员、管理成员或战略成员。",
                "risk": "如果保护原因过期，可能造成低贡献成员长期占位。",
            },
            {
                "name": "降级观察",
                "benefit": "保留成员，同时要求后续恢复贡献。",
                "risk": "需要组长持续跟进。",
            },
            {
                "name": "取消保护并转清理候选",
                "benefit": "释放名额，强化纪律。",
                "risk": "可能影响组织稳定或战场部署。",
            },
        ],
        "decision": {
            "action": "keep_or_review_protection",
            "label": "保护对象：暂缓清理，进入复核",
            "confidence": _confidence_protection(member),
            "reason": "该成员命中保护规则，不能按普通低活跃成员直接清理。",
        },
        "execution": [
            "确认该成员当前保护原因是否仍然有效。",
            "如果仍承担管理、门神、铺路、器械或核心战斗任务，继续保护。",
            "如果保护原因已经失效，转入观察或清理候选。",
        ],
        "review": {
            "next_check": "下一次身份中心复核",
            "success_condition": "保护原因明确，并且角色价值仍然存在。",
            "failure_condition": "保护原因缺失、长期无贡献、组长无法说明用途。",
        },
    }


def reason_member_growth(member: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    成员培养推理。
    """
    name = _member_name(member)
    if not name:
        return None

    av = _to_float(_get(member, "av", "active_value", "activity"))
    bs = _to_float(_get(member, "bs", "stability_value", "stability"))
    trend = _get(member, "trend", default="")
    risk_level = _get(member, "risk_level", "risk", default="")
    identity_score = _to_float(_get(member, "identity_score", default=0)) or 0

    good_score = av is not None and bs is not None and av >= HIGH_AV and bs >= HIGH_BS
    good_trend = trend in ("up", "explosive")
    good_identity = identity_score >= HIGH_IDENTITY
    safe_risk = risk_level not in ("danger", "clear")

    if not (good_score and good_trend and safe_risk):
        return None

    facts = _base_member_facts(member)
    reasoning = [
        {
            "rule": "high_activity_and_stability",
            "logic": f"活跃度 >= {HIGH_AV} 且 稳定度 >= {HIGH_BS}",
            "conclusion": "该成员近期贡献稳定，具备培养价值。",
        },
        {
            "rule": "positive_trend",
            "logic": "趋势为 up / explosive",
            "conclusion": "该成员仍处在成长状态，适合重点关注。",
        },
    ]

    if good_identity:
        reasoning.append({
            "rule": "high_identity_score",
            "logic": f"身份评分 >= {HIGH_IDENTITY}",
            "conclusion": "该成员不仅活跃，而且具备较高组织价值。",
        })

    return {
        "target_type": "member",
        "target_name": name,
        "decision_type": "growth",
        "facts": facts,
        "reasoning": reasoning,
        "options": [
            {
                "name": "重点培养",
                "benefit": "提升骨干储备，增强联盟长期战斗力。",
                "risk": "需要管理层投入沟通和资源。",
            },
            {
                "name": "安排战场任务",
                "benefit": "通过实战验证成员能力。",
                "risk": "任务过重可能导致成员压力过大。",
            },
            {
                "name": "继续普通观察",
                "benefit": "不增加管理成本。",
                "risk": "可能错过培养窗口。",
            },
        ],
        "decision": {
            "action": "mark_as_growth_target",
            "label": "重点培养候选",
            "confidence": _confidence_growth(member),
            "reason": "该成员活跃、稳定且趋势向上，适合纳入培养池。",
        },
        "execution": [
            "安排组长主动沟通，确认成员意愿。",
            "优先分配明确战场任务或团队协作任务。",
            "观察下一轮快照中战功、助攻、捐献或势力是否继续增长。",
        ],
        "review": {
            "next_check": "下一次快照",
            "success_condition": "继续保持高活跃、高稳定或趋势上升。",
            "failure_condition": "活跃下降、稳定下降或任务执行无反馈。",
        },
    }


def reason_groups(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    分组推理。

    当前第一版只基于 report 中已有 group_warnings。
    不重新访问数据库。
    """
    results: List[Dict[str, Any]] = []

    for group in report.get("group_warnings", []) or []:
        group_name = _get(group, "group_name", "name", default="未知分组")
        avg_av = _to_float(_get(group, "avg_av", default=None))
        avg_bs = _to_float(_get(group, "avg_bs", default=None))
        down_count = _to_int(_get(group, "down_count", default=0))

        facts = [
            _fact("avg_av", "平均活跃度", avg_av, "分组整体活跃水平"),
            _fact("avg_bs", "平均稳定度", avg_bs, "分组整体稳定水平"),
            _fact("down_count", "下滑成员数", down_count, "分组内趋势下滑成员数量"),
        ]

        reasoning = []

        if avg_av is not None and avg_av < MID_AV:
            reasoning.append({
                "rule": "group_low_activity",
                "logic": f"分组平均活跃度 < {MID_AV}",
                "conclusion": "该分组整体活跃不足，需要组长介入。",
            })

        if avg_bs is not None and avg_bs < MID_BS:
            reasoning.append({
                "rule": "group_low_stability",
                "logic": f"分组平均稳定度 < {MID_BS}",
                "conclusion": "该分组成员状态不稳定，可能存在执行力下降。",
            })

        if down_count >= 3:
            reasoning.append({
                "rule": "group_many_down_members",
                "logic": "下滑成员数 >= 3",
                "conclusion": "该分组存在集体下滑迹象，需要重点排查。",
            })

        if not reasoning:
            continue

        results.append({
            "target_type": "group",
            "target_name": group_name,
            "decision_type": "group_warning",
            "facts": facts,
            "reasoning": reasoning,
            "options": [
                {
                    "name": "要求组长当天反馈",
                    "benefit": "快速确认分组状态。",
                    "risk": "可能增加组长管理压力。",
                },
                {
                    "name": "抽查重点成员",
                    "benefit": "能快速定位问题成员。",
                    "risk": "可能遗漏整体组织问题。",
                },
                {
                    "name": "暂缓处理",
                    "benefit": "避免短期波动造成误判。",
                    "risk": "如果是真实下滑，会错过干预窗口。",
                },
            ],
            "decision": {
                "action": "ask_group_leader_review",
                "label": "分组预警：建议组长复核",
                "confidence": 0.75,
                "reason": "该分组命中活跃、稳定或趋势下滑规则。",
            },
            "execution": [
                "要求组长确认分组成员在线和任务执行情况。",
                "优先排查连续下滑成员。",
                "下一次快照复核该分组平均活跃度和稳定度。",
            ],
            "review": {
                "next_check": "下一次快照",
                "success_condition": "分组平均活跃度或稳定度回升。",
                "failure_condition": "分组继续下滑或风险成员继续增加。",
            },
        })

    return results


def reason_alliance(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    全盟层面推理。

    第一版只做轻量汇总，不做复杂战略判断。
    后续 Simulation Engine 再做多方案推演。
    """
    total_members = _to_int(_get(report, "total_members", "member_count", default=0))
    management_tasks = report.get("management_tasks", []) or []
    future_risks = report.get("future_risks", []) or []
    growth_targets = report.get("growth_targets", []) or []

    results: List[Dict[str, Any]] = []

    if len(management_tasks) >= 8 or len(future_risks) >= 8:
        results.append({
            "target_type": "alliance",
            "target_name": "全盟",
            "decision_type": "alliance_management_pressure",
            "facts": [
                _fact("total_members", "成员总数", total_members, "当前系统识别的成员规模"),
                _fact("management_tasks", "管理任务数", len(management_tasks), "今日需要处理的管理任务数量"),
                _fact("future_risks", "潜在风险数", len(future_risks), "未来可能恶化的成员数量"),
                _fact("growth_targets", "培养候选数", len(growth_targets), "当前可培养成员数量"),
            ],
            "reasoning": [
                {
                    "rule": "high_management_pressure",
                    "logic": "管理任务数或潜在风险数较多",
                    "conclusion": "当前联盟管理压力偏高，需要优先处理风险，再考虑培养。",
                }
            ],
            "options": [
                {
                    "name": "优先处理风险",
                    "benefit": "快速降低主盟不稳定因素。",
                    "risk": "可能暂时牺牲培养节奏。",
                },
                {
                    "name": "风险与培养并行",
                    "benefit": "既处理问题，也不耽误骨干建设。",
                    "risk": "对管理层执行力要求较高。",
                },
                {
                    "name": "暂不集中处理",
                    "benefit": "减少管理动作。",
                    "risk": "风险可能继续累积。",
                },
            ],
            "decision": {
                "action": "risk_first_management",
                "label": "全盟策略：风险优先",
                "confidence": 0.78,
                "reason": "当前管理任务或潜在风险数量偏多，应先降低风险。",
            },
            "execution": [
                "先处理高风险成员和分组预警。",
                "再安排重点培养对象。",
                "将无法确认状态的成员转入下一轮复核。",
            ],
            "review": {
                "next_check": "下一次 AI 日报或幕僚中心刷新",
                "success_condition": "高风险任务数量下降。",
                "failure_condition": "风险任务继续增加或分组预警扩大。",
            },
        })

    return results


def build_reasoning_summary(
    member_reasoning: List[Dict[str, Any]],
    group_reasoning: List[Dict[str, Any]],
    alliance_reasoning: List[Dict[str, Any]],
) -> str:
    cleanup_count = _count_by_type(member_reasoning, "cleanup")
    protect_count = _count_by_type(member_reasoning, "protection")
    growth_count = _count_by_type(member_reasoning, "growth")
    group_count = len(group_reasoning)
    alliance_count = len(alliance_reasoning)

    if not any([cleanup_count, protect_count, growth_count, group_count, alliance_count]):
        return "当前未发现需要重点推理的高风险、保护或培养对象，联盟状态暂时稳定。"

    parts = []

    if cleanup_count:
        parts.append(f"发现 {cleanup_count} 名清理候选成员")

    if protect_count:
        parts.append(f"发现 {protect_count} 名需要保护或复核的成员")

    if growth_count:
        parts.append(f"发现 {growth_count} 名重点培养候选")

    if group_count:
        parts.append(f"发现 {group_count} 个分组存在预警")

    if alliance_count:
        parts.append("全盟层面存在管理压力")

    return "；".join(parts) + "。"


def _reasoning_priority(item: Dict[str, Any]) -> float:
    """
    推理展示优先级。

    只用于排序，不参与最终业务判断。
    """
    decision_type = item.get("decision_type", "")
    confidence = _to_float(
        item.get("decision", {}).get("confidence", 0)
    ) or 0

    facts = {
        fact.get("key"): fact.get("value")
        for fact in item.get("facts", [])
        if isinstance(fact, dict)
    }

    av = _to_float(facts.get("av"))
    bs = _to_float(facts.get("bs"))
    stall_count = _to_int(facts.get("stall_count"))
    trend = facts.get("trend", "")
    risk_level = facts.get("risk_level", "")

    score = confidence * 100

    if decision_type == "cleanup":
        if av is not None:
            score += max(0, 40 - av)
        if bs is not None:
            score += max(0, 45 - bs)
        if trend in ("down", "dead"):
            score += 10
        if risk_level in ("danger", "clear"):
            score += 10
        score += min(stall_count * 2, 20)

    elif decision_type == "protection":
        identity_score = _to_float(facts.get("identity_score")) or 0
        wv = _to_float(facts.get("wv")) or 0
        score += identity_score * 0.3
        score += wv * 0.2
        if risk_level in ("danger", "clear"):
            score += 10

    elif decision_type == "growth":
        if av is not None:
            score += av * 0.2
        if bs is not None:
            score += bs * 0.2
        if trend == "explosive":
            score += 15
        elif trend == "up":
            score += 8

    return round(score, 2)


def _collect_members_from_report(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从 report 中尽可能收集成员对象。

    兼容不同 Engine 的输出字段。
    不要求 staff_engine 改结构。
    """
    candidate_keys = [
        "members",
        "all_members",
        "raw_members",
        "today_actions",
        "action_list",
        "management_tasks",
        "growth_targets",
        "protect_targets",
        "future_risks",
        "watch_members",
        "clean_members",
        "train_members",
    ]

    members: List[Dict[str, Any]] = []
    seen = set()

    for key in candidate_keys:
        items = report.get(key, []) or []
        if isinstance(items, dict):
            items = list(items.values())

        for item in items:
            if not isinstance(item, dict):
                continue

            # 有些 task 会把成员信息包在 member 字段里
            member = item.get("member") if isinstance(item.get("member"), dict) else item

            name = _member_name(member)
            if not name:
                continue

            if name in seen:
                continue

            seen.add(name)
            members.append(member)

    return members


def _base_member_facts(member: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        _fact("member", "成员", _member_name(member), "被分析对象"),
        _fact("group_name", "分组", _get(member, "group_name", default=""), "成员所在分组"),
        _fact("role_tag", "身份", _get(member, "role_tag", default="member"), "成员身份标签"),
        _fact("av", "活跃度", _get(member, "av", "active_value", "activity", default=None), "近期活跃贡献水平"),
        _fact("bs", "稳定度", _get(member, "bs", "stability_value", "stability", default=None), "近期行为稳定程度"),
        _fact("trend", "趋势", _get(member, "trend", default=""), "最近周期变化方向"),
        _fact("risk_level", "风险等级", _get(member, "risk_level", "risk", default=""), "系统识别的风险级别"),
        _fact("risk_reason", "风险原因", _get(member, "risk_reason", default=""), "触发风险的主要原因"),
        _fact("identity_score", "身份评分", _get(member, "identity_score", default=None), "组织身份与长期价值评分"),
        _fact("wv", "战争价值", _get(member, "wv", "war_value", default=None), "战场贡献价值"),
        _fact("stall_count", "连续停滞", _get(member, "stall_count", default=0), "连续没有明显增长的周期数"),
    ]


def _fact(key: str, label: str, value: Any, meaning: str) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "meaning": meaning,
    }


def _member_name(member: Dict[str, Any]) -> str:
    value = _get(
        member,
        "member",
        "member_name",
        "name",
        "target_name",
        "player_name",
        default="",
    )
    return str(value).strip() if value is not None else ""


def _get(data: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if isinstance(data, dict) and key in data:
            return data.get(key)

        if hasattr(data, key):
            return getattr(data, key)

    return default


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _count_by_type(items: List[Dict[str, Any]], decision_type: str) -> int:
    return sum(1 for item in items if item.get("decision_type") == decision_type)


def _confidence_cleanup(member: Dict[str, Any]) -> float:
    av = _to_float(_get(member, "av", default=None))
    bs = _to_float(_get(member, "bs", default=None))
    risk_level = _get(member, "risk_level", "risk", default="")
    trend = _get(member, "trend", default="")
    stall_count = _to_int(_get(member, "stall_count", default=0))

    score = 0.55

    if av is not None and av < LOW_AV:
        score += 0.10

    if bs is not None and bs < LOW_BS:
        score += 0.10

    if risk_level in ("danger", "clear"):
        score += 0.10

    if trend in ("down", "dead"):
        score += 0.08

    if stall_count >= 5:
        score += 0.07

    return round(min(score, 0.95), 2)


def _confidence_protection(member: Dict[str, Any]) -> float:
    score = 0.60

    if _to_int(_get(member, "is_protected", default=0)) == 1:
        score += 0.15

    identity_score = _to_float(_get(member, "identity_score", default=0)) or 0
    if identity_score >= HIGH_IDENTITY:
        score += 0.10

    wv = _to_float(_get(member, "wv", "war_value", default=0)) or 0
    if wv >= HIGH_WAR_VALUE:
        score += 0.10

    role_tag = _get(member, "role_tag", default="")
    if role_tag in ("admin", "leader", "core", "protected"):
        score += 0.10

    return round(min(score, 0.95), 2)


def _confidence_growth(member: Dict[str, Any]) -> float:
    score = 0.60

    identity_score = _to_float(_get(member, "identity_score", default=0)) or 0
    if identity_score >= HIGH_IDENTITY:
        score += 0.10

    trend = _get(member, "trend", default="")
    if trend == "explosive":
        score += 0.12
    elif trend == "up":
        score += 0.08

    av = _to_float(_get(member, "av", default=None))
    bs = _to_float(_get(member, "bs", default=None))

    if av is not None and av >= 80:
        score += 0.07

    if bs is not None and bs >= 80:
        score += 0.07

    return round(min(score, 0.95), 2)
