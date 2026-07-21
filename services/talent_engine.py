def get_talent_type(member):

    av = member.get("av", 0)

    bs = member.get("bs", 0)

    identity = member.get(
        "identity_score",
        0
    )

    trend = member.get(
        "trend",
        "stable"
    )

    # 战神型
    if av >= 70 and identity >= 80:
        return "战神型"

    # 将才型
    if bs >= 80 and identity >= 70:
        return "将才型"

    # 肝帝型
    if av >= 70:
        return "肝帝型"

    # 潜力股
    if trend == "explosive":
        return "潜力股"

    # 稳定骨干
    if bs >= 60:
        return "稳定骨干"

    return "普通成员"


def build_member_strategy(member):
    """
    生成人物档案顶部AI管理建议。

    风险状态优先于身份评分：
    protected > clear > danger > warning > safe。

    身份评分低不能单独产生清理结论。
    """
    member = member or {}

    talent = get_talent_type(
        member
    )

    identity_score = float(
        member.get(
            "identity_score",
            0,
        )
        or 0
    )

    risk_level = str(
        member.get(
            "risk_level",
            "",
        )
        or ""
    ).strip()

    is_protected = bool(
        member.get(
            "is_protected",
            0,
        )
    )

    if (
        is_protected
        or risk_level == "protected"
    ):
        return {
            "level": "★★★★★",
            "title": "战略保护",
            "talent": talent,
            "decision":
                "已进入身份保护名单",
            "actions": [
                "保持身份保护标记",
                "结合战略用途安排资源",
                "禁止自动进入清理名单",
            ],
        }

    if risk_level == "clear":
        return {
            "level": "★☆☆☆☆",
            "title": "清理复核",
            "talent": talent,
            "decision":
                "进入人工复核，不自动清理",
            "actions": [
                "核查最近5期有效贡献",
                "确认请假、铺路、门神、小号或器械号等特殊情况",
                "由组长复核后决定是否进入清理名单",
            ],
        }

    if risk_level == "danger":
        return {
            "level": "★☆☆☆☆",
            "title": "重点核查",
            "talent": talent,
            "decision":
                "风险较高，但暂不直接清理",
            "actions": [
                "联系本人确认实际状态",
                "由组长核查特殊身份和近期任务",
                "下一次有效快照继续复查",
            ],
        }

    if risk_level == "warning":
        return {
            "level": "★★☆☆☆",
            "title": "观察复核",
            "talent": talent,
            "decision":
                "近期存在有效贡献，暂不进入清理名单",
            "actions": [
                "继续观察近期贡献",
                "跟踪战功、助攻和捐献变化",
                "下一阶段由组长复核",
                "暂不清理",
            ],
        }

    if identity_score >= 90:
        return {
            "level": "★★★★★",
            "title": "核心成员",
            "talent": talent,
            "decision": "长期保留",
            "actions": [
                "重点保护",
                "资源倾斜",
                "核心战役优先",
                "禁止清理",
            ],
        }

    if identity_score >= 70:
        return {
            "level": "★★★★☆",
            "title": "重点培养",
            "talent": talent,
            "decision": "重点培养对象",
            "actions": [
                "纳入重点培养名单",
                "安排高级任务",
                "持续跟踪贡献表现",
                "优先参与核心战役",
            ],
        }

    if identity_score >= 50:
        return {
            "level": "★★★☆☆",
            "title": "持续观察",
            "talent": talent,
            "decision": "观察成长空间",
            "actions": [
                "持续观察",
                "跟踪活跃变化",
                "保持正常资源投入",
            ],
        }

    if identity_score >= 30:
        return {
            "level": "★★☆☆☆",
            "title": "风险观察",
            "talent": talent,
            "decision": "需要继续跟踪",
            "actions": [
                "观察近期贡献",
                "沟通活跃情况",
                "结合下一阶段表现复查",
            ],
        }

    return {
        "level": "★★☆☆☆",
        "title": "待观察",
        "talent": talent,
        "decision":
            "身份评分较低，但不能仅凭评分清理",
        "actions": [
            "补充观察近期贡献",
            "由组长确认实际状态",
            "结合风险等级决定后续措施",
        ],
    }
