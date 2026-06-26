def calculate_health_score(member):

    score = 100

    score -= max(
        0,
        (60-member["av"])
    )

    score -= max(
        0,
        (60-member["bs"])
    )

    score -= member["stall_count"] * 5

    return max(0,int(score))


def build_root_member_analysis(report):

    target_group = (
        report["group_diagnosis"]["group"]
    )

    members = report["members"]

    group_members = [

        m
        for m in members
        if m.get("group_name") == target_group

    ]

    bad_members = []

    for m in group_members:

        # =====================
        # 战略保护过滤
        # =====================

        if m.get("role_tag") in (

            "admin",
            "leader"

        ):
           continue

        if m.get(
            "identity_score",
            0
        ) >= 70:
            continue

        health = (

            m.get("av",0)
            +
            m.get("bs",0)

        ) / 2

        bad_members.append({

            "member":
                m.get("member_name"),

            "av":
                round(
                    m.get("av",0),
                    1
                ),

            "bs":
                round(
                    m.get("bs",0),
                    1
                ),

            "health":
                round(
                    health,
                    1
                ),

            "identity":
                round(
                    m.get(
                        "identity_score",
                        0
                    ),
                    1
                ),

            "role":
                m.get(
                    "role_tag",
                    "member"
                ),

            "reason":
                m.get(
                    "risk_reason",
                    ""
                )

        })

    bad_members.sort(

        key=lambda x:
            x["health"]

    )

    return {

        "group": target_group,

        "root_members":

            bad_members[:5]

    }

def build_intervention_targets(report):

    members = report["members"]

    targets = []

    for m in members:

        # =====================
        # 管理层过滤
        # =====================

        if m.get("role_tag") in (
            "admin",
            "leader"
        ):
            continue

        trend = m.get(
            "trend",
            "stable"
        )

        risk = m.get(
            "risk_level",
            ""
        )

        # =====================
        # 培养对象排除
        # =====================

        if trend in (
            "up",
            "explosive"
        ):
            continue

        # =====================
        # 必须满足干预条件
        # =====================

        if (
            trend != "down"
            and
            risk != "danger"
        ):
            continue

        av = m.get("av", 0)

        bs = m.get("bs", 0)

        identity = m.get(
            "identity_score",
            0
        )

        health = (
            av + bs
        ) / 2

        # =====================
        # AI干预价值评分
        # =====================

        score = 0

        # 身份价值越高越值得救
        score += identity

        # 健康度越差越值得关注
        score += max(
            0,
            60 - health
        )

        # 下滑趋势加权
        if trend == "down":
            score += 20

        # danger成员额外加权
        if risk == "danger":
            score += 20

        # 已彻底废掉的人价值降低
        if health < 10:
            score -= 30

        targets.append({

            "member":
                m["member_name"],

            "identity":
                round(
                    identity,
                    1
                ),

            "health":
                round(
                    health,
                    1
                ),

            "trend":
                trend,

            "risk":
                risk,

            "intervention_score":
                round(
                    score,
                    1
                )

        })

    targets.sort(
        key=lambda x:
            x["intervention_score"],
        reverse=True
    )

    return targets[:10]

def build_cleanup_targets(report):

    members = report["members"]
    targets = []

    for m in members:

        # 管理层不清理
        if m.get("role_tag") in (
            "admin",
            "leader"
        ):
            continue

        identity = m.get(
            "identity_score",
            0
        )

        av = m.get(
            "av",
            0
        )

        bs = m.get(
            "bs",
            0
        )

        trend = m.get(
            "trend",
            ""
        )

        health = (
            av + bs
        ) / 2

        # 清理标准

        if health > 15:
            continue

        if trend != "dead":
            continue

        if identity >= 30:
            continue

        targets.append({

            "member":
                m.get(
                    "member_name"
                ),

            "identity":
                round(
                    identity,
                    1
                ),

            "health":
                round(
                    health,
                    1
                ),

            "trend":
                trend,

            "reason":
                m.get(
                    "risk_reason",
                    ""
                )

        })

    targets.sort(

        key=lambda x:
            x["health"]

    )

    return targets[:10]

def build_member_engine(report):

    report["root_member_analysis"] = (
        build_root_member_analysis(report)
    )

    report["cleanup_targets"] = (
        build_cleanup_targets(report)
    )

    report["intervention_targets"] = (
        build_intervention_targets(report)
    )

    return report