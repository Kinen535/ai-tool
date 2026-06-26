def build_stage_strategy(report):

    stage = report["war_stage"]

    if stage == "开荒期":

        return {

            "stage": stage,

            "goal": "快速完成开荒",

            "focus": "活跃度",

            "actions": [

                "提高上线率",

                "完成资源州铺路",

                "提升整体发育速度"

            ]

        }

    elif stage == "发育期":

        return {

            "stage": stage,

            "goal": "培养核心战力",

            "focus": "成长成员",

            "actions": [

                "培养重点成员",

                "优化分组结构",

                "储备战争资源"

            ]

        }

    elif stage == "对抗期":

        return {

            "stage": stage,

            "goal": "压制敌盟",

            "focus": "执行力",

            "actions": [

                "处理风险成员",

                "提升在线率",

                "加强集结执行"

            ]

        }

    else:

        return {

            "stage": stage,

            "goal": "全力决战",

            "focus": "战争贡献",

            "actions": [

                "清理长期停滞成员",

                "保留核心战力",

                "集中资源决战"

            ]

        }

def build_strategy_simulation(report):

    alliance = report.get(
        "alliance_status",
        {}
    )

    war = report.get(
        "war_contribution_analysis",
        {}
    )

    future_risks = report.get(
        "future_risks",
        []
    )

    cleanup_targets = report.get(
        "cleanup_targets",
        []
    )

    battle_power = alliance.get(
        "score",
        0
    )

    top_group = war.get(
        "top_group",
        "暂无"
    )

    weak_group = war.get(
        "weak_group",
        "暂无"
    )

    future_count = len(
        future_risks
    )

    cleanup_count = len(
        cleanup_targets
    )

    if future_count >= 10:

        future_level = "高"

    elif future_count >= 5:

        future_level = "中"

    else:

        future_level = "低"

    if battle_power >= 80:

        battle_judgement = "联盟战力充足，具备主动进攻能力"

    elif battle_power >= 60:

        battle_judgement = "联盟处于警戒状态，需要稳住执行力"

    else:

        battle_judgement = "联盟战力承压，需要优先整顿组织"

    suggestion = (
        f"当前核心战组为{top_group}，"
        f"风险战组为{weak_group}。"
        f"建议优先整顿{weak_group}，"
        f"预计减少{future_count}名潜在风险成员。"
    )

    expected_gain = (
        f"+8%战争贡献，减少{cleanup_count}名长期停滞成员影响"
    )

    return {

        "battle_power":
            battle_power,

        "battle_judgement":
            battle_judgement,

        "top_group":
            top_group,

        "weak_group":
            weak_group,

        "future_level":
            future_level,

        "future_count":
            future_count,

        "cleanup_count":
            cleanup_count,

        "suggestion":
            suggestion,

        "expected_gain":
            expected_gain

    }

def build_strategy_simulation_v2(report):

    alliance = report.get(
        "alliance_status",
        {}
    )

    current_score = alliance.get(
        "score",
        0
    )

    future_risks = report.get(
        "future_risks",
        []
    )

    cleanup_targets = report.get(
        "cleanup_targets",
        []
    )

    growth_targets = report.get(
        "growth_targets",
        []
    )

    risk_count = len(
        future_risks
    )

    cleanup_count = len(
        cleanup_targets
    )

    growth_count = len(
        growth_targets
    )

    future_score = max(
        0,
        current_score - risk_count
    )

    plans = []

    # ==================
    # 方案A
    # ==================

    plans.append({

        "name":
            "整顿风险分组",

        "gain":
            4,

        "risk":
            1,

        "score":
            8

    })

    # ==================
    # 方案B
    # ==================

    plans.append({

        "name":
            "清理长期停滞成员",

        "gain":
            cleanup_count,

        "risk":
            2,

        "score":
            cleanup_count * 1.5

    })

    # ==================
    # 方案C
    # ==================

    plans.append({

        "name":
            "培养成长成员",

        "gain":
            growth_count,

        "risk":
            0,

        "score":
            growth_count

    })

    plans.sort(
        key=lambda x:x["score"],
        reverse=True
    )

    best_plan = plans[0]

    return {

        "current_score":
            current_score,

        "future_score":
            future_score,

        "risk_change":
            f"+{risk_count}",

        "recommended_plan":
            best_plan["name"],

        "plans":
            plans

    }

def build_strategy_simulation_v25(report):

    groups = report.get(
        "group_war_scores",
        []
    )

    future_risks = report.get(
        "future_risks",
        []
    )

    if not groups:

        return {}

    # ==================
    # 联盟真实战力
    # ==================

    alliance_power = round(

        sum(
            x["war_score"]
            for x in groups
        ) / len(groups),

        1

    )

    # ==================
    # 风险预测
    # ==================

    future_score = round(

        alliance_power
        -
        len(future_risks) * 1.5,

        1

    )

    # ==================
    # 最强分组
    # ==================

    top_group = max(

        groups,

        key=lambda x:
        x["war_score"]

    )

    # ==================
    # 最弱分组
    # ==================

    weak_group = min(

        groups,

        key=lambda x:
        x["war_score"]

    )

    # ==================
    # 最危险3个分组
    # ==================

    focus_groups = sorted(

        groups,

        key=lambda x:
        x["war_score"]

    )[:3]

    # ==================
    # AI建议
    # ==================

    suggestion = (

        f"优先整顿"
        f"{weak_group['group']}，"
        f"预计可提升联盟战力。"

    )

    return {

        "current_power":
            alliance_power,

        "future_power":
            future_score,

        "top_group":
            top_group,

        "weak_group":
            weak_group,

        "focus_groups":
            focus_groups,

        "suggestion":
            suggestion

    }

def build_decision_impact(report):

    alliance = report.get(
        "alliance_status",
        {}
    )

    current_score = alliance.get(
        "score",
        0
    )

    cleanup_count = len(
        report.get(
            "cleanup_targets",
            []
        )
    )

    growth_count = len(
        report.get(
            "growth_targets",
            []
        )
    )

    risk_count = len(
        report.get(
            "future_risks",
            []
        )
    )

    predicted_gain = round(
        cleanup_count * 0.4 +
        growth_count * 0.3 -
        risk_count * 0.1,
        1
    )

    future_score = round(
        current_score +
        predicted_gain,
        1
    )

    confidence = min(
        95,
        60 + growth_count
    )

    return {

        "before_score":
            current_score,

        "after_score":
            future_score,

        "power_gain":
            predicted_gain,

        "risk_reduce":
            cleanup_count,

        "confidence":
            confidence

    }

def build_strategy_engine(report):

    report["stage_strategy"] = (
        build_stage_strategy(report)
    )

    report["strategy_simulation"] = (
        build_strategy_simulation(report)
    )

    report["strategy_v2"] = (
        build_strategy_simulation_v2(report)
    )

    report["decision_impact"] = (
        build_decision_impact(report)
    )

    report["strategy_v25"] = (
        build_strategy_simulation_v25(report)
    )

    return report