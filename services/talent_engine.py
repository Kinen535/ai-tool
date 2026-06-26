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

    talent = get_talent_type(member)

    identity_score = member.get(
        "identity_score",
        0
    )

    # =====================
    # AI最终结论
    # =====================

    if identity_score >= 90:

        return {
            "level":"★★★★★",
            "title":"核心成员",
            "talent":talent,
            "decision":"长期保留",
            "actions":[
                "重点保护",
                "资源倾斜",
                "核心战役优先",
                "禁止清理"
            ]
        }

    elif identity_score >= 70:

        return {
            "level":"★★★★☆",
            "title":"重点培养",
            "talent":talent,
            "decision":"重点培养对象",
            "actions":[
                "纳入重点培养名单",
                "安排高级任务",
                "观察未来3期表现",
                "优先参与核心战役"
            ]
        }

    elif identity_score >= 50:

        return {
            "level":"★★★☆☆",
            "title":"持续观察",
            "talent":talent,
            "decision":"观察成长空间",
            "actions":[
                "持续观察",
                "跟踪活跃变化",
                "保持资源投入"
            ]
        }

    elif identity_score >= 30:

        return {
            "level":"★★☆☆☆",
            "title":"风险观察",
            "talent":talent,
            "decision":"存在流失风险",
            "actions":[
                "重点观察",
                "沟通活跃情况",
                "未来2期复查"
            ]
        }

    return {
        "level":"★☆☆☆☆",
        "title":"建议清理",
        "talent":talent,
        "decision":"长期价值较低",
        "actions":[
            "移入观察名单",
            "停止资源倾斜",
            "未来3期无改善则清理"
        ]
    }