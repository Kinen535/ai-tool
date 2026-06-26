def build_command_center(report):

    center = {}

    risk_count = len(report["today_actions"])
    growth_count = len(report["growth_targets"])
    future_count = len(report["future_risks"])

    # =====================
    # AI总参谋结论
    # =====================

    if risk_count >= 10:

        summary = (
            f"联盟当前存在 {risk_count} 名风险成员，"
            f"风险规模较大。"
            f"建议今天优先处理风险名单，"
            f"暂停新增培养计划。"
        )

    elif growth_count >= 10:

        summary = (
            f"联盟当前出现 {growth_count} 名成长成员，"
            f"整体状态良好。"
            f"建议启动重点培养计划。"
        )

    elif future_count >= 10:

        summary = (
            f"未来风险成员达到 {future_count} 人。"
            f"建议提前安排组长跟进。"
        )

    else:

        summary = (
            "联盟整体状态稳定。"
            "建议持续观察核心成员变化。"
        )

    center["summary"] = summary

    # =====================
    # 今日最紧急
    # =====================

    urgent_members = []

    for item in report["today_actions"][:3]:

        urgent_members.append({
            "member": item["member"],
            "reason": item["reason"]
        })

    center["urgent"] = {
        "count": risk_count,
        "members": urgent_members
    }

    # =====================
    # 重点培养
    # =====================

    growth_members = []

    for item in report["growth_targets"][:5]:

        growth_members.append({
            "member": item["member"],
            "reason": item["reason"]
        })

    center["growth"] = growth_members

    # =====================
    # 未来风险
    # =====================

    future_members = []

    for item in report["future_risks"][:5]:

        future_members.append({
            "member": item["member"],
            "reason": item["reason"]
        })

    center["future"] = future_members

    # =====================
    # 今日核心任务
    # =====================

    if report["group_analysis"]:

        worst_group = min(
            report["group_analysis"],
            key=lambda x: x["health"]
        )

        center["mission"] = {

            "title":"处理最危险分组",

            "target":worst_group["group"],

            "reason":
                f"健康度 {worst_group['health']}",

            "actions":[

                "联系组长",

                "排查风险成员",

                "优化成员结构"

            ],

            "gain":"+8联盟评分"
        }

    else:

        center["mission"] = {

            "title":"维持观察",

            "target":"无",

            "reason":"暂无异常",

            "actions":[
                "持续观察"
            ],

            "gain":"稳定"
        }

    return center

def build_battle_order(report):

    mission = report["command_center"]["mission"]

    return {

        "title": mission["title"],

        "target": mission["target"],

        "reason": mission["reason"],

        "steps":[

            "联系负责人",

            "确认问题成员",

            "提交处理方案"

        ],

        "priority":"P1",

        "deadline":"24小时"

    }

def build_daily_orders(report):

    orders = []

    stage = report.get(
        "war_stage",
        "对抗期"
    )

    cleanup = report.get(
        "cleanup_targets",
        []
    )

    intervention = report.get(
        "intervention_targets",
        []
    )

    growth = report.get(
        "growth_targets",
        []
    )

    # =====================
    # 决战期：先战争冲刺
    # =====================

    if stage == "决战期":

        orders.append({

            "priority":"P1",

            "title":"战争贡献冲刺",

            "count":0,

            "members":[],

            "action":"集中主力参与战争"

        })

        if intervention:

            orders.append({

                "priority":"P2",

                "title":"干预下滑成员",

                "count":len(intervention),

                "members":[
                    x["member"]
                    for x in intervention[:5]
                ],

                "action":"安排组长跟进，防止战力流失"

            })

        if cleanup:

            orders.append({

                "priority":"P3",

                "title":"处理长期停滞成员",

                "count":len(cleanup),

                "members":[
                    x["member"]
                    for x in cleanup[:5]
                ],

                "action":"核查状态并执行清理"

            })

        return orders

    # =====================
    # 对抗期：先干预，再清理，再培养
    # =====================

    if stage == "对抗期":

        if intervention:

            orders.append({

                "priority":"P1",

                "title":"干预下滑成员",

                "count":len(intervention),

                "members":[
                    x["member"]
                    for x in intervention[:5]
                ],

                "action":"安排组长跟进，防止战力流失"

            })

        if cleanup:

            orders.append({

                "priority":"P2",

                "title":"处理长期停滞成员",

                "count":len(cleanup),

                "members":[
                    x["member"]
                    for x in cleanup[:5]
                ],

                "action":"核查状态并执行清理"

            })

        if growth:

            orders.append({

                "priority":"P3",

                "title":"保持培养计划",

                "count":len(growth),

                "members":[
                    x["member"]
                    for x in growth[:5]
                ],

                "action":"维持成长节奏"

            })

        return orders

    # =====================
    # 发育期：培养优先
    # =====================

    if stage == "发育期":

        if growth:

            orders.append({

                "priority":"P1",

                "title":"培养核心成员",

                "count":len(growth),

                "members":[
                    x["member"]
                    for x in growth[:5]
                ],

                "action":"纳入重点培养名单"

            })

        if intervention:

            orders.append({

                "priority":"P2",

                "title":"干预下滑成员",

                "count":len(intervention),

                "members":[
                    x["member"]
                    for x in intervention[:5]
                ],

                "action":"安排组长跟进"

            })

        if cleanup:

            orders.append({

                "priority":"P3",

                "title":"处理长期停滞成员",

                "count":len(cleanup),

                "members":[
                    x["member"]
                    for x in cleanup[:5]
                ],

                "action":"核查状态并执行清理"

            })

        return orders

    # =====================
    # 开荒期：活跃与发育优先
    # =====================

    if growth:

        orders.append({

            "priority":"P1",

            "title":"快速培养成员",

            "count":len(growth),

            "members":[
                x["member"]
                for x in growth[:5]
            ],

            "action":"资源向成长成员倾斜"

        })

    if intervention:

        orders.append({

            "priority":"P2",

            "title":"干预下滑成员",

            "count":len(intervention),

            "members":[
                x["member"]
                for x in intervention[:5]
            ],

            "action":"安排组长跟进"

        })

    if cleanup:

        orders.append({

            "priority":"P3",

            "title":"观察长期停滞成员",

            "count":len(cleanup),

            "members":[
                x["member"]
                for x in cleanup[:5]
            ],

            "action":"暂缓清理，先确认是否战略小号"

        })

    return orders

def build_commander_brief(report):

    growth = report.get(
        "growth_targets",
        []
    )

    intervention = report.get(
        "intervention_targets",
        []
    )

    cleanup = report.get(
        "cleanup_targets",
        []
    )

    # =====================
    # P1 清理优先
    # =====================

    if len(cleanup) >= 5:

        return {

            "decision":
                "清理长期停滞成员",

            "priority":
                "P1",

            "reason":[

                f"发现 {len(cleanup)} 名长期停滞成员",

                "联盟存在组织冗余",

                "需要释放管理资源"

            ],

            "today_focus":[

                x["member"]

                for x in cleanup[:3]

            ],

            "expected_gain":

                "提升联盟活跃度"

        }

    # =====================
    # P2 干预优先
    # =====================

    elif len(intervention) >= 5:

        return {

            "decision":
                "挽救核心下滑成员",

            "priority":
                "P1",

            "reason":[

                f"发现 {len(intervention)} 名高价值下滑成员",

                "存在战力流失风险",

                "需要组长介入"

            ],

            "today_focus":[

                x["member"]

                for x in intervention[:3]

            ],

            "expected_gain":

                "降低战力流失"

        }

    # =====================
    # P3 培养优先
    # =====================

    else:

        return {

            "decision":
                "培养核心成员",

            "priority":
                "P1",

            "reason":[

                "暂无待清理成员",

                "暂无高价值干预对象",

                f"培养名单共 {len(growth)} 人"

            ],

            "today_focus":[

                x["member"]

                for x in growth[:3]

            ],

            "expected_gain":

                "提升联盟整体战力"

        }

def build_command_engine(report):

    result = {}

    result["command_center"] = (
        build_command_center(report)
    )

    report["command_center"] = (
        result["command_center"]
    )

    result["battle_order"] = (
        build_battle_order(report)
    )

    report["battle_order"] = (
        result["battle_order"]
    )

    result["daily_orders"] = (
        build_daily_orders(report)
    )

    report["daily_orders"] = (
        result["daily_orders"]
    )

    result["commander_brief"] = (
        build_commander_brief(report)
    )

    report["commander_brief"] = (
        result["commander_brief"]
    )

    report.update(
        result
    )

    return report