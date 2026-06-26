from __future__ import annotations

# =========================
# 玩家活跃分类
# =========================
def classify_player(activity_list: list[float]) -> str:

    if not activity_list:
        return "无数据"

    avg = sum(activity_list) / len(activity_list)

    variance = (
        sum((x - avg) ** 2 for x in activity_list)
        / len(activity_list)
    )

    last3 = (
        activity_list[-3:]
        if len(activity_list) >= 3
        else activity_list
    )

    inactive_count = sum(
        1 for x in last3 if x < 10
    )

    if avg > 70:

        if variance < 400:
            return "🔥 核心稳定成员"

        return "⚡ 核心波动成员"

    if avg > 30:

        if inactive_count >= 2:
            return "⚠️ 疑似流失"

        return "🙂 普通成员"

    if inactive_count >= 3:
        return "❌ 清理候选"

    return "🧊 低活跃成员"


# =========================
# AI 风险评分系统
# =========================
def calculate_ai_risk(member_data):

    score = 0

    battle_growth = member_data.get(
        "battle_growth", 0
    )

    assist_growth = member_data.get(
        "assist_growth", 0
    )

    power_growth = member_data.get(
        "power_growth", 0
    )

    # =========================
    # 战功异常
    # =========================

    if battle_growth > 30:

        score += 35

    elif battle_growth > 20:

        score += 25

    elif battle_growth > 10:

        score += 15

    # =========================
    # 助攻异常
    # =========================

    if (
        battle_growth > 20
        and assist_growth < 5
    ):

        score += 20

    # =========================
    # 势力异常
    # =========================

    if power_growth > 15:

        score += 15

    # =========================
    # 稳定成员减分
    # =========================

    if (
        battle_growth < 10
        and assist_growth > 5
        and power_growth < 10
    ):

        score -= 10

    # =========================
    # 分数限制
    # =========================

    score = max(0, min(score, 100))

    # =========================
    # 风险等级
    # =========================

    if score >= 80:

        level = "高风险"

    elif score >= 60:

        level = "中风险"

    elif score >= 30:

        level = "观察"

    else:

        level = "稳定"

    return {
        "score": score,
        "level": level
    }