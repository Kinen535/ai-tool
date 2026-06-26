from services.group_engine import *
from services.alliance_engine import *
from collections import defaultdict
from services.engines.decision_engine import (
    build_decision_engine
)
from services.engines.command_engine import (
    build_command_engine
)

from services.engines.strategy_engine import (
    build_strategy_engine
)

from services.engines.member_engine import (
    calculate_health_score,
    build_member_engine
)
from services.engines.alliance_engine import (
    build_alliance_engine
)

from services.engines.reasoning_engine import (
    build_reasoning_report
)

from services.engines.simulation_engine import (
    build_simulation_report
)

from services.engines.execution_planner import (
    build_execution_plan_report
)

from services.v11_memory_store import (
    build_current_v11_snapshot_key,
    load_previous_v11_strategy_snapshot,
    save_v11_strategy_snapshot,
    save_v11_reflection_record,
    load_v11_reflection_history
)

from services.engines.reflection_engine import (
    build_reflection_report
)

from services.engines.learning_engine import (
    build_learning_report
)

from services.engines.llm_layer import (
    build_llm_explanation_report
)

from services.v12_feedback_store import (
    load_execution_feedback_records,
    load_execution_feedback_logs
)

from services.engines.execution_feedback_engine import (
    build_execution_feedback_report
)

from services.engines.execution_feedback_audit_engine import (
    build_execution_feedback_audit_report
)

def build_staff_report(conn):

    report = {}

    members = load_members(conn)

    report["members"] = members

    report["conn"] = conn

    # =====================
    # 战争阶段
    # =====================

    report["war_stage"] = (
        detect_war_stage_by_date(
            get_current_battle_start_date(conn)
        )
    )

    # =====================
    # 基础名单
    # =====================

    report["management_tasks"] = (
        build_task_pool(members)
    )

    report["today_actions"] = (
        get_today_actions(members)
    )

    report["growth_targets"] = (
        get_growth_targets(members)
    )

    report["protect_targets"] = (
        get_protect_targets(members)
    )

    report["future_risks"] = (
        get_future_risks(members)
    )

    report["group_warnings"] = (
        get_group_warnings(members)
    )

    # =====================
    # 联盟基础分析
    # =====================

    #report["decision_list"] = (
    #    build_decision_list(report)
    #)

    #report["summary"] = (
     #   build_summary(report)
   # )
    report = (
        build_alliance_engine(report)
    )

    #report["ai_decisions"] = (
     #   build_ai_decisions(report)
   # )

    report["alliance_status"] = (
        build_alliance_status(report)
    )

    report["alliance_conclusion"] = (
        build_alliance_conclusion(
            report["alliance_status"]
        )
    )

    report["alliance_decision"] = (
        build_alliance_decision(
            report["alliance_status"]
        )
    )

    # =====================
    # 分组分析
    # =====================

    group_analysis = (
        build_group_analysis(
            members
        )
    )

    report["group_analysis"] = (
        group_analysis
    )

    report["group_war_scores"] = (
        build_group_war_scores(
            members
        )
    )

    report["group_summary"] = (
        build_group_summary(
            group_analysis
        )
    )

    report["alliance_strategy"] = (
        build_alliance_strategy(
            report["alliance_status"],
            report["group_analysis"]
        )
    )

    # =====================
    # 指挥中心
    # command_center 必须在 group_diagnosis / battle_order 前生成
    # =====================

    report = (
        build_command_engine(report)
    )

    report["group_diagnosis"] = (
        build_group_diagnosis(report)
    )

    # =====================
    # 目标名单
    # =====================
    report = (
        build_member_engine(report)
    )

    # =====================
    # 军令系统
    # =====================

    # =====================
    # 战争分析
    # =====================

    report["war_contribution_analysis"] = (
        build_war_contribution_analysis(report)
    )
   
    # =====================
    # 决策系统
    # 顺序必须是：影响评估 → 可信度 → 最终决策 → 执行计划
    # =====================

    report = (
        build_strategy_engine(report)
    )

    report = (
        build_decision_engine(report)
    )

    # =====================
    # V11 推理系统
    # staff_engine 只负责调度，推理逻辑由 reasoning_engine 完成
    # =====================

    report["reasoning_report"] = (
        build_reasoning_report(report)
    )

    report["v11_simulation_report"] = (
        build_simulation_report(report)
    )

    report["v11_execution_plan"] = (
        build_execution_plan_report(report)
    )

    # =====================
    # V11 复盘系统
    # staff_engine 只负责调度与数据 I/O
    # reflection_engine 只负责复盘推理
    # =====================

    current_v11_snapshot_key = (
        build_current_v11_snapshot_key(report)
    )

    report["current_v11_snapshot_key"] = (
        current_v11_snapshot_key
    )

    report["v12_feedback_records"] = (
        load_execution_feedback_records(
            conn,
            current_v11_snapshot_key
        )
    )

    report["v12_execution_feedback"] = (
        build_execution_feedback_report(report)
    )

    report["v12_feedback_logs"] = (
        load_execution_feedback_logs(
            conn,
            current_v11_snapshot_key,
            limit=50
        )
    )

    report["v12_feedback_audit"] = (
        build_execution_feedback_audit_report(report)
    )

    report["previous_v11_snapshot"] = (
        load_previous_v11_strategy_snapshot(
            conn,
            current_v11_snapshot_key
        )
    )

    report["v11_reflection_report"] = (
        build_reflection_report(report)
    )

    save_v11_reflection_record(
        conn,
        current_v11_snapshot_key,
        report
    )

    report["v11_reflection_history"] = (
        load_v11_reflection_history(
            conn,
            limit=20
        )
    )

    report["v11_learning_report"] = (
        build_learning_report(report)
    )

    report["v11_llm_report"] = (
        build_llm_explanation_report(report)
    )

    save_v11_strategy_snapshot(
        conn,
        report
    )

    return report


def build_management_tasks(members):

    tasks = []

    for m in members:

        health = calculate_health_score(m)

        if health < 30:

            tasks.append({
                "level":"🔴紧急",
                "member":m["member_name"],
                "reason":"综合健康度过低",
                "action":"立即联系确认状态",
                "score":100-health
            })

        elif health < 50:

            tasks.append({
                "level":"🟡重要",
                "member":m["member_name"],
                "reason":"健康度下降明显",
                "action":"安排组长跟进",
                "score":80-health
            })

    tasks.sort(
        key=lambda x:x["score"],
        reverse=True
    )

    return tasks[:10]



def build_task_pool(members):

    tasks = []

    for m in members:

        health = calculate_health_score(m)

        priority = 0
        task_type = ""
        action = ""

        # P1 风险任务
        if health < 30:

            priority = 100 - health

            task_type = "风险处理"

            action = "立即联系确认状态"

        # P2 培养任务
        elif (
            m["trend"] in ("up", "explosive")
            and m["av"] >= 50
            and m["risk_level"] != "danger"
        ):

            priority = 70

            task_type = "重点培养"

            action = "纳入重点培养名单"

        # P3 观察任务
        elif (
            m["trend"] == "down"
            and m["bs"] < 60
        ):

            priority = 40

            task_type = "持续观察"

            action = "观察未来3天变化"

        else:
            continue

        tasks.append({

            "priority": priority,

            "member": m["member_name"],

            "group": m["group_name"],

            "type": task_type,

            "action": action,

            "health": health
        })

    tasks.sort(
        key=lambda x: x["priority"],
        reverse=True
    )

    risk_tasks = [
        t for t in tasks
        if t["type"] == "风险处理"
    ][:5]

    growth_tasks = [
        t for t in tasks
        if t["type"] == "重点培养"
    ][:3]

    watch_tasks = [
        t for t in tasks
        if t["type"] == "持续观察"
    ][:2]

    return (
        risk_tasks
        + growth_tasks
        + watch_tasks
    )

def load_members(conn):
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        member,
        group_name,
        av,
        bs,
        wv,
        bv,
        trend,
        risk_level,
        risk_reason,
        stall_count,
        identity_score,
        role_tag
    FROM player_records
    WHERE snapshot_time = (
        SELECT MAX(snapshot_time)
        FROM player_records
    )
    """)

    rows = cursor.fetchall()

    members = []

    for r in rows:
        members.append({

            "member_name": r[0],
            "group_name": r[1],

            "av": r[2] or 0,
            "bs": r[3] or 0,

            "wv": r[4] or 0,
            "bv": r[5] or 0,

            "trend": r[6] or "stable",

            "risk_level": r[7] or "safe",
            "risk_reason": r[8] or "",

            "stall_count": r[9] or 0,

            "identity_score": r[10] or 0,

            "role_tag": r[11] or "member"

        })
    return members


def get_today_actions(members):
    result = []

    for m in members:
        risk = m["risk_level"]
        av = m["av"]
        bs = m["bs"]
        trend = m["trend"]
        stall = m["stall_count"]
        role = m["role_tag"]

        if role in ["admin", "leader"]:
            continue

        if risk == "danger":
            result.append({
                "member": m["member_name"],
                "priority": "P1",
                "reason": m["risk_reason"] or "风险等级较高",
                "action": "建议今日私聊确认状态"
            })

        elif stall >= 7:
            result.append({
                "member": m["member_name"],
                "priority": "P1",
                "reason": f"连续停滞 {stall} 次",
                "action": "建议确认是否弃坑或暂离"
            })

        elif trend == "down" and av < 30:
            result.append({
                "member": m["member_name"],
                "priority": "P2",
                "reason": "活跃度下降明显",
                "action": "建议观察并由组长提醒"
            })

    return result[:10]


def get_growth_targets(members):

    result = []

    for m in members:

        score = 0

        # 爆发成长
        if m["trend"] == "explosive":
            score += 40

        elif m["trend"] == "up":
            score += 25

        # 活跃度
        score += min(30, m["av"] / 2)

        # 稳定度
        score += min(20, m["bs"] / 3)

        # 身份价值
        score += min(10, m["identity_score"])

        if (
            score >= 40
            and m["risk_level"] not in (
                "danger",
                "clear"
            )
        ):

           result.append({

               "member": m["member_name"],

               "reason": "成长趋势良好",

               "action": "建议纳入重点培养名单",

               "score": round(score, 1),

               "av": round(m["av"], 1),

               "bs": round(m["bs"], 1),

              "identity_score": round(
                  m["identity_score"],
                  1
              ),

              "trend": m["trend"]
         })
               
    result.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return result[:10]


def get_protect_targets(members):
    result = []

    for m in members:
        if (
            m["risk_level"] == "danger"
            and (
                m["wv"] >= 60
                or m["trend"] == "stable"
            )
        ):
            result.append({
                "member": m["member_name"],
                "reason": "表面风险较高，但战争价值或趋势仍有支撑",
                "action": "暂缓清理，建议继续观察"
            })

    return result[:10]


def get_future_risks(members):
    result = []

    for m in members:
        if (
            m["risk_level"] != "danger"
            and m["trend"] == "down"
            and m["av"] < 40
            and m["bs"] < 50
        ):
            result.append({
                "member": m["member_name"],
                "probability": "高",
                "reason": "活跃度、稳定度持续下降",
                "action": "预计未来可能进入风险名单"
            })

    return result[:10]


def get_group_warnings(members):

    groups = {}

    for m in members:

        group = m["group_name"]

        if not group:
            continue

        if group not in groups:

            groups[group] = {
                "total": 0,
                "danger": 0,
                "down": 0,
                "stall": 0
            }

        groups[group]["total"] += 1

        if m["risk_level"] == "danger":
            groups[group]["danger"] += 1

        if m["trend"] == "down":
            groups[group]["down"] += 1

        if m["stall_count"] >= 3:
            groups[group]["stall"] += 1

    result = []

    for group, data in groups.items():

        health = (
            100
            - data["danger"] * 5
            - data["down"] * 2
            - data["stall"] * 2
        )

        result.append({
            "group": group,
            "health": max(0, health),
            "danger": data["danger"],
            "down": data["down"],
            "stall": data["stall"]
        })

    result.sort(
        key=lambda x: x["health"]
    )

    return result[:10]

def build_action_list(members):

    actions = []

    # P1 风险处理

    for m in members:

        if m["risk_level"] == "danger":

            actions.append({
                "priority": "P1",
                "member": m["member_name"],
                "title": "立即关注风险成员",
                "reason": m["risk_reason"]
            })

    # P1 未来风险

    for m in members:

        if (
            m["risk_level"] != "danger"
            and m["trend"] == "down"
            and m["av"] < 40
            and m["bs"] < 50
        ):

            actions.append({
                "priority": "P1",
                "member": m["member_name"],
                "title": "提前干预",
                "reason": "预计未来进入风险名单"
            })

    # P2 培养

    for m in members:

        if (
            m["av"] >= 70
            and m["bs"] >= 70
            and m["trend"] == "up"
        ):

            actions.append({
                "priority": "P2",
                "member": m["member_name"],
                "title": "重点培养",
                "reason": "近期成长明显"
            })

    return actions[:10]


def build_group_diagnosis(report):

    mission = report["command_center"]["mission"]

    target_group = mission["target"]

    members = load_members(
        report["conn"]
    )

    group_members = [

        m
        for m in members
        if m.get("group_name") == target_group

    ]

    member_count = len(
        group_members
    )

    risk_members = len([

        m
        for m in group_members
        if m.get("risk_level") == "danger"

    ])

    avg_av = 0
    avg_bs = 0

    if member_count:

        avg_av = round(

            sum(
                m["av"]
                for m in group_members
            )
            /
            member_count,

            1

        )

        avg_bs = round(

            sum(
                m["bs"]
                for m in group_members
            )
            /
            member_count,

            1

        )

    risk_rate = 0

    if member_count:

        risk_rate = round(

            risk_members
            * 100
            / member_count,

            1

        )

    if risk_rate >= 30:

        main_problem = "风险成员过多"

    elif avg_av < 40:

        main_problem = "活跃度过低"

    elif avg_bs < 40:

        main_problem = "稳定度过低"

    else:

        main_problem = "整体状态一般"

    return {

        "group": target_group,

        "member_count": member_count,

        "risk_members": risk_members,

        "risk_rate": risk_rate,

        "avg_av": avg_av,

        "avg_bs": avg_bs,

        "main_problem": main_problem

    }

def get_current_battle_start_date(conn):

    cur = conn.cursor()

    row = cur.execute("""

        select battle_start_date

        from battles

        where is_current = 1

        limit 1

    """).fetchone()

    if not row:
        return None

    return row[0]

def build_war_contribution_analysis(report):

    scores = report.get(
        "group_war_scores",
        []
    )

    if not scores:

        return {

            "top_group":"暂无",

            "top_score":0,

            "weak_group":"暂无",

            "weak_score":0,

            "focus_groups":[],

            "suggestion":"暂无数据"

        }

    top = scores[0]

    weak = scores[-1]

    focus_groups = [

        {

            "group":
                x["group"],

            "war_score":
                x["war_score"]

        }

        for x in scores[-3:]

    ]

    return {

        "top_group":
            top["group"],

        "top_score":
            top["war_score"],

        "weak_group":
            weak["group"],

        "weak_score":
            weak["war_score"],

        "focus_groups":
            focus_groups,

        "suggestion":
            "优先提升战争贡献最低的分组执行力"

    }


def build_group_war_scores(members):

    groups = {}

    trend_map = {

        "explosive": 100,
        "up": 80,
        "stable": 60,
        "down": 30,
        "dead": 0

    }

    for m in members:

        group = m.get(
            "group_name",
            "未分组"
        )

        if group not in groups:

            groups[group] = []

        groups[group].append(m)

    result = []

    for group_name, rows in groups.items():

        count = len(rows)

        if count == 0:
            continue

        avg_wv = sum(
            x.get("wv", 0)
            for x in rows
        ) / count

        avg_av = sum(
            x.get("av", 0)
            for x in rows
        ) / count

        avg_identity = sum(
            x.get(
                "identity_score",
                0
            )
            for x in rows
        ) / count

        avg_trend = sum(

            trend_map.get(
                x.get(
                    "trend",
                    "stable"
                ),
                60
            )

            for x in rows

        ) / count

        raw_score = (

            avg_wv * 0.5

            +

            avg_av * 0.2

            +

            avg_trend * 0.2

            +

            avg_identity * 0.1

        )

        war_score = min(

            100,

            round(
                raw_score * 1.8,
                1
            )

        )

        if group_name in (

            "",
            "无门阀",
            "未分组"

        ):
            continue

        result.append({

            "group":
                group_name,

            "war_score":
                round(
                    war_score,
                    1
                ),

            "avg_wv":
                round(
                    avg_wv,
                    1
                ),

            "avg_av":
                round(
                    avg_av,
                    1
                ),

            "avg_identity":
                round(
                    avg_identity,
                    1
                )

        })

    result.sort(

        key=lambda x:
            x["war_score"],

        reverse=True

    )

    return result







