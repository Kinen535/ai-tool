def build_decision_list(report):

    decisions = []

    # 重点培养
    for item in report["growth_targets"][:3]:

        decisions.append({

            "member": item["member"],

            "decision": "重点培养",

            "confidence": 95,

            "reason": item["reason"],

            "color": "green",

            "evidences":[

                f"活跃指数较高（{item['av']}）",

                f"综合贡献优秀（{item['bs']}）",

                f"身份价值达到A级（{item['identity_score']}）",

                "近期处于爆发增长阶段"

            ],

            "analysis": (
                f"{item['member']}近期成长趋势明显，"
                f"综合贡献持续提升，"
                f"当前身份价值达到A级骨干标准，"
                f"暂无明显风险。"
            ),

            "recommendation":[

                "纳入重点培养名单",

                "安排高级任务",

                "观察未来3期表现",

                "优先参与核心战役"

            ],

            "actions": [

                "纳入重点培养名单",

                "未来3期持续观察"

            ]

        })

    # 风险成员
    for item in report["today_actions"][:3]:

        decisions.append({

            "member": item["member"],

            "decision": "重点关注",

            "confidence": 90,

            "reason": item["reason"],

            "color": "red",

        })

    # 未来风险
    for item in report["future_risks"][:3]:

        decisions.append({

            "member": item["member"],

            "decision": "提前观察",

            "confidence": 80,

            "reason": item["reason"],

            "color": "orange",

        })

    return decisions[:10]

def build_summary(report):

    if not report["group_warnings"]:
        return "当前盟内整体状态稳定"

    worst_group = report["group_warnings"][0]

    risk_count = len(report["today_actions"])
    growth_count = len(report["growth_targets"])
    future_count = len(report["future_risks"])

    return (
        f"今日待处理任务 {risk_count + growth_count + future_count} 项；"
        f"风险处理 {risk_count} 项；"
        f"重点培养 {growth_count} 项；"
        f"未来风险预警 {future_count} 项。\n\n"
        f"当前风险最高分组：{worst_group['group']} "
        f"(健康度 {worst_group['health']})。\n\n"
        f"建议优先处理风险成员，并关注成长趋势良好的培养对象。"
    )

def build_ai_decisions(report):

    decisions = []

    # ① 风险分组深度判断
    if report["group_warnings"]:

        worst = report["group_warnings"][0]

        if worst["health"] < 50:
            level = "P1"
            judgment = "该分组已经进入高风险状态，优先处理。"
        elif worst["health"] < 70:
            level = "P2"
            judgment = "该分组存在明显波动，需要持续观察。"
        else:
            level = "P3"
            judgment = "该分组整体可控，暂不需要强干预。"

        decisions.append({
            "level": level,
            "title": "风险分组处置",
            "content": (
                f"{worst['group']} 当前健康度 {worst['health']}，"
                f"风险成员 {worst['danger']} 人。"
                f"{judgment}建议组长今日排查风险成员。"
            )
        })

    # ② 培养资源建议
    if report["growth_targets"]:

        top_growth = report["growth_targets"][0]

        decisions.append({
            "level": "P2",
            "title": "培养资源倾斜",
            "content": (
                f"当前发现 {len(report['growth_targets'])} 名成长成员。"
                f"其中 {top_growth['member']} 培养指数较高，"
                f"建议优先纳入重点培养名单。"
            )
        })

    # ③ 风险成员处置
    if report["today_actions"]:

        top_risk = report["today_actions"][0]

        decisions.append({
            "level": "P1",
            "title": "风险成员沟通",
            "content": (
                f"当前存在 {len(report['today_actions'])} 名重点风险成员。"
                f"建议优先联系 {top_risk['member']}，"
                f"确认是否继续活跃或需要清理。"
            )
        })

    # ④ 未来风险提前干预
    if report["future_risks"]:

        top_future = report["future_risks"][0]

        decisions.append({
            "level": "P2",
            "title": "未来风险预防",
            "content": (
                f"发现 {len(report['future_risks'])} 名潜在风险成员。"
                f"其中 {top_future['member']} 已出现下降迹象，"
                f"建议提前观察，避免后续进入清理名单。"
            )
        })

    return decisions

def build_alliance_engine(report):

    report["decision_list"] = (
        build_decision_list(report)
    )

    report["summary"] = (
        build_summary(report)
    )

    report["ai_decisions"] = (
        build_ai_decisions(report)
    )

    return report