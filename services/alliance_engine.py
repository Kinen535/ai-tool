from datetime import datetime

def build_alliance_status(report):

    risk_count = len(
        report["today_actions"]
    )

    growth_count = len(
        report["growth_targets"]
    )

    future_count = len(
        report["future_risks"]
    )

    score = 100

    score -= risk_count * 3

    score -= future_count * 2

    score += growth_count * 1

    score = max(
        0,
        min(100, score)
    )

    if score >= 80:

        stage = "健康"

    elif score >= 60:

        stage = "警戒"

    else:

        stage = "危险"

    return {

        "score": score,

        "stage": stage,

        "risk_count": risk_count,

        "growth_count": growth_count,

        "future_count": future_count

    }

def build_alliance_decision(status):

    score = status["score"]

    risk = status["risk_count"]

    growth = status["growth_count"]

    future = status["future_count"]

    if risk >= 10:

        return {
            "title":"优先处理风险成员",
            "reason":"风险成员数量过高",
            "action":"暂停新增培养计划",
            "impact":"+12健康度"
        }

    elif growth >= 10:

        return {
            "title":"集中培养核心成员",
            "reason":"成长成员数量较多",
            "action":"资源向培养名单倾斜",
            "impact":"+8战力提升"
        }

    else:

        return {
            "title":"保持观察",
            "reason":"联盟状态稳定",
            "action":"维持当前策略",
            "impact":"稳定发展"
        }

def build_alliance_strategy(
    alliance_status,
    group_analysis
):

    score = alliance_status["score"]

    risk = alliance_status["risk_count"]

    growth = alliance_status["growth_count"]

    future = alliance_status["future_count"]

    worst_group = {}

    if group_analysis:

        worst_group = min(
            group_analysis,
            key=lambda x: x["health"]
        )

    # =========================
    # 组织整顿模式
    # =========================

    if (
        score < 50
        or (
            worst_group
            and worst_group.get("health", 100) < 30
        )
    ):

        return {

            "strategy": "组织整顿模式",

            "priority": "P1",

            "goal": "恢复组织活力",

            "confidence": 92,

            "reason": [

                f"最危险分组：{worst_group.get('group', '未知')}",

                f"分组健康度：{worst_group.get('health', 0)}",

                "组织结构出现明显问题"

            ],

            "actions": [

                "召开组长会议",

                "检查分组管理",

                "调整人员结构"

            ],

            "expected_gain": "+10组织活力"
        }

    # =========================
    # 风险治理模式
    # =========================

    elif (
        risk >= growth
        and risk >= 10
    ):

        return {

            "strategy": "风险治理模式",

            "priority": "P1",

            "goal": "降低联盟风险",

            "confidence": 88,

            "reason": [

                f"风险成员 {risk} 人",

                f"未来风险 {future} 人",

                "风险规模超过成长规模"

            ],

            "actions": [

                "处理高风险成员",

                "联系停滞成员",

                "暂停新增培养计划"

            ],

            "expected_gain": "+12健康度"
        }

    # =========================
    # 人才培养模式
    # =========================

    elif (
        growth > risk
        and growth >= 10
    ):

        return {

            "strategy": "人才培养模式",

            "priority": "P1",

            "goal": "提升核心战力",

            "confidence": 85,

            "reason": [

                f"培养对象 {growth} 人",

                f"风险成员仅 {risk} 人",

                "联盟进入人才成长窗口"

            ],

            "actions": [

                "培养TOP10成员",

                "安排高级任务",

                "增加核心战役参与"

            ],

            "expected_gain": "+8战力提升"
        }

    # =========================
    # 战力冲刺模式
    # =========================

    elif (
        score >= 80
        and risk <= 5
    ):

        return {

            "strategy": "战力冲刺模式",

            "priority": "P1",

            "goal": "扩大联盟优势",

            "confidence": 90,

            "reason": [

                f"联盟评分 {score}",

                f"风险成员仅 {risk} 人",

                "联盟整体状态优秀"

            ],

            "actions": [

                "资源向核心组倾斜",

                "扩大活跃成员规模",

                "重点培养尖刀组"

            ],

            "expected_gain": "+15战力提升"
        }

    # =========================
    # 稳定发育模式
    # =========================

    else:

        return {

            "strategy": "稳定发育模式",

            "priority": "P2",

            "goal": "维持稳定发展",

            "confidence": 75,

            "reason": [

                "联盟状态整体稳定",

                "暂无重大风险",

                "适合持续发育"

            ],

            "actions": [

                "保持当前策略",

                "观察风险变化",

                "持续培养骨干"

            ],

            "expected_gain": "稳定增长"
        }

def build_alliance_conclusion(status):

    score = status["score"]

    risk_count = status["risk_count"]

    growth_count = status["growth_count"]

    if risk_count >= 10:

        return (
            "联盟当前风险成员较多，"
            "建议优先处理风险名单，"
            "暂停新增培养计划。"
        )

    if growth_count >= 10:

        return (
            "联盟成长成员较多，"
            "建议集中资源培养核心战力。"
        )

    if score >= 80:

        return (
            "联盟整体运行稳定。"
        )

    return (
        "联盟进入警戒阶段，"
        "建议持续观察。"
    )

def detect_war_stage(members):

    avg_av = sum(
        m["av"]
        for m in members
    ) / max(len(members),1)

    avg_wv = sum(
        m["wv"]
        for m in members
    ) / max(len(members),1)

    if avg_wv < 20:
        return "开荒期"

    elif avg_wv < 40:
        return "发育期"

    elif avg_wv < 70:
        return "对抗期"

    else:
        return "决战期"

def detect_war_stage_by_date(battle_start_date):

    days = (
        datetime.now()
        -
        datetime.strptime(
            battle_start_date,
            "%Y-%m-%d"
        )
    ).days

    if days <= 7:
        return "开荒期"

    elif days <= 20:
        return "发育期"

    elif days <= 45:
        return "对抗期"

    else:
        return "决战期"

def detect_war_stage_by_date(battle_start_date):

    if not battle_start_date:
        return "未知阶段"

    try:

        start_date = datetime.strptime(
            battle_start_date,
            "%Y-%m-%d"
        )

        days = (
            datetime.now() - start_date
        ).days

        if days <= 7:
            return "开荒期"

        elif days <= 20:
            return "发育期"

        elif days <= 45:
            return "对抗期"

        else:
            return "决战期"

    except:

        return "未知阶段"