def build_decision_compare(report):

    plans = report.get(
        "strategy_v2",
        {}
    ).get(
        "plans",
        []
    )

    confidence = report.get(
        "decision_confidence",
        {}
    ).get(
        "confidence",
        70
    )

    current_score = report.get(
        "alliance_status",
        {}
    ).get(
        "score",
        0
    )

    result = []

    for item in plans:

        future_score = (
            current_score
            + item.get("gain", 0)
            - item.get("risk", 0)
        )

        total_score = (
            item.get("score", 0) * 5
            + confidence * 0.3
        )

        result.append({

            "name":
                item["name"],

            "gain":
                item["gain"],

            "risk":
                item["risk"],

            "future_score":
                round(future_score, 1),

            "confidence":
                confidence,

            "total_score":
                round(total_score, 1)

        })

    result.sort(

        key=lambda x: x["total_score"],

        reverse=True

    )

    return {

        "recommended":
            result[0]["name"],

        "plans":
            result

    }

def build_decision_confidence(report):

    future_risks = len(
        report.get(
            "future_risks",
            []
        )
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

    alliance_score = report.get(
        "alliance_status",
        {}
    ).get(
        "score",
        0
    )

    confidence = 60

    confidence += min(
        cleanup_count,
        10
    )

    confidence += min(
        growth_count,
        10
    )

    confidence -= min(
        future_risks,
        10
    )

    confidence = max(
        50,
        min(confidence,95)
    )

    predicted_gain = round(

        cleanup_count * 0.4
        +
        growth_count * 0.3,

        1

    )

    predicted_risk = max(

        0,

        future_risks
        -
        cleanup_count // 2

    )

    return {

        "confidence":
            confidence,

        "current_score":
            alliance_score,

        "future_score":
            round(
                alliance_score
                +
                predicted_gain,
                1
            ),

        "future_risk":
            predicted_risk,

        "risk_delta":
            future_risks
            -
            predicted_risk

    }

def build_final_decision(report):

    plans = report.get(
        "strategy_v2",
        {}
    ).get(
        "plans",
        []
    )

    if not plans:
        return {}

    best = max(
        plans,
        key=lambda x: x["score"]
    )

    decision = best["name"]

    confidence_data = report.get(
        "decision_confidence",
        {}
    )

    if decision == "清理长期停滞成员":

        reason = [
            "长期停滞成员数量过多",
            "影响联盟执行力",
            "释放管理资源收益最高"
        ]

    elif decision == "培养成长成员":

        reason = [
            "成长成员数量较多",
            "培养收益较高",
            "适合长期建设"
        ]

    else:

        reason = [
            "风险分组占比较高",
            "需要恢复分组健康度",
            "降低未来风险"
        ]

    return {

        "decision": decision,

        "priority": "最高",

        "expected_power": f"+{best['gain']}",

        "risk_reduce": f"-{best['risk']}",

        "confidence": confidence_data.get(
            "confidence",
            70
        ),

        "future_score": confidence_data.get(
            "future_score",
            0
        ),

        "future_risk": confidence_data.get(
            "future_risk",
            0
        ),

        "reason": reason

    }

def build_reasoning_chain(report):

    alliance = report.get(
        "alliance_status",
        {}
    )

    confidence = report.get(
        "decision_confidence",
        {}
    )

    final = report.get(
        "final_decision",
        {}
    )

    future_risks = len(
        report.get(
            "future_risks",
            []
        )
    )

    cleanup = len(
        report.get(
            "cleanup_targets",
            []
        )
    )

    return {

        "title": "AI决策推理",

        "steps": [

            {

                "icon": "📊",

                "title": "联盟现状",

                "impact": "中",

                "content":
                    f"联盟综合评分 {alliance.get('score',0)} 分，目前整体执行力需要持续提升。"

            },

            {

                "icon": "⚠",

                "title": "发现问题",

                "impact": "高",

                "content":
                    f"检测到 {cleanup} 名长期停滞成员，未来风险成员 {future_risks} 人。"

            },

            {

                "icon": "📉",

                "title": "趋势预测",

                "impact": "高",

                "content":
                    f"预计执行后联盟评分提升至 {confidence.get('future_score',0)} 分，风险成员下降至 {confidence.get('future_risk',0)} 人。"

            },

            {

                "icon": "🧠",

                "title": "AI推理",

                "impact": "高",

                "content":
                    "综合风险收益比分析，长期停滞成员对联盟执行力影响最大，因此优先处理。"

            },

            {

                "icon": "🎯",

                "title": "最终决策",

                "impact": "最高",

                "content":
                    f"建议立即执行「{final.get('decision','暂无决策')}」。"

            }

        ]

    }

def build_execution_plan(report):

    final_decision = report.get(
        "final_decision",
        {}
    )

    decision = final_decision.get(
        "decision",
        ""
    )

    if decision == "清理长期停滞成员":

        return {

            "today":[

                "核查10名长期停滞成员状态",

                "联系组长确认是否保留",

                "整理候选清理名单"

            ],

            "tomorrow":[

                "执行第一批清理",

                "统计释放位置",

                "更新风险中心"

            ],

            "this_week":[

                "补充成长成员",

                "优化分组结构",

                "重新评估联盟健康度"

            ]

        }

    elif decision == "培养成长成员":

        return {

            "today":[

                "确认重点培养名单",

                "安排资源倾斜"

            ],

            "tomorrow":[

                "跟踪成长速度",

                "记录培养效果"

            ],

            "this_week":[

                "补充核心梯队",

                "建立储备干部名单"

            ]

        }

    else:

        return {

            "today":[

                "统计风险分组"

            ],

            "tomorrow":[

                "安排组长整改"

            ],

            "this_week":[

                "完成分组整顿"

            ]

        }


def build_decision_engine(report):

    result = {}

    result["decision_compare"] = (
        build_decision_compare(report)
    )

    # 先放进去，后面逐步迁
    report["decision_compare"] = (
        result["decision_compare"]
    )

    result["decision_confidence"] = (
        build_decision_confidence(report)
    )

    report["decision_confidence"] = (
        result["decision_confidence"]
    )

    result["final_decision"] = (
        build_final_decision(report)
    )

    report["final_decision"] = (
        result["final_decision"]
    )

    result["reasoning_chain"] = (
        build_reasoning_chain(report)
    )

    report["reasoning_chain"] = (
        result["reasoning_chain"]
    )

    result["execution_plan"] = (
        build_execution_plan(report)
    )

    report.update(
        result
    )

    return report