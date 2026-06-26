from collections import defaultdict


def build_group_analysis(members):

    groups = defaultdict(list)

    for m in members:

        group_name = (
            m.get("group_name")
            or "未分组"
        )

        groups[group_name].append(m)

    results = []

    for group_name, rows in groups.items():

        total = len(rows)

        if total == 0:
            continue

        avg_av = sum(
            m.get("av", 0)
            for m in rows
        ) / total

        avg_bs = sum(
            m.get("bs", 0)
            for m in rows
        ) / total

        risk_count = sum(
            1
            for m in rows
            if m.get("risk_level")
            in ("warning", "danger")
        )

        growth_count = sum(
            1
            for m in rows
            if m.get("trend")
            in ("up", "explosive")
        )

        health_score = (
            avg_av * 0.4
            + avg_bs * 0.4
            + max(
                0,
                100 - risk_count * 5
            ) * 0.2
        )

        results.append({

            "group": group_name,

            "health": round(
                health_score,
                1
            ),

            "avg_av": round(
                avg_av,
                1
            ),

            "avg_bs": round(
                avg_bs,
                1
            ),

            "risk_count": risk_count,

            "growth_count": growth_count,

            "members": total

        })

    results.sort(
        key=lambda x: x["health"],
        reverse=True
    )

    return results

def build_group_summary(groups):

    if not groups:

        return {}

    return {

        "best_group":
            groups[0],

        "worst_group":
            groups[-1],

        "growth_group":
            max(
                groups,
                key=lambda x:
                x["growth_count"]
            ),

        "risk_group":
            max(
                groups,
                key=lambda x:
                x["risk_count"]
            )

    }