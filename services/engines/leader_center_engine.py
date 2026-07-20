from __future__ import annotations

from typing import Any, Dict, List

from services.v14_leader_mapping_store import (
    load_leader_mappings,
    load_leader_mapping_logs,
)


def build_leader_center_report(conn, staff_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    V14 组长协同驾驶舱 / 分组责任中心

    Phase A:
    - 不写数据库
    - 不改 V12 反馈逻辑
    - 从最新成员快照 + V12 执行反馈任务中聚合分组压力
    """

    members = _fetch_latest_members(conn)
    member_map = _build_member_map(members)

    task_report = staff_report.get("v12_execution_feedback", {}) or {}
    tasks = task_report.get("tasks", []) or []

    manual_mappings = load_leader_mappings(conn)
    mapping_logs = load_leader_mapping_logs(conn, limit=20)

    group_stats = _build_group_member_stats(members)
    _merge_task_stats(group_stats, tasks, member_map)

    group_cards = _finalize_group_cards(
        group_stats,
        manual_mappings
    )
    leader_pressure = _build_leader_pressure(group_cards)
    owner_pressure = _build_owner_pressure(tasks)
    high_pressure_groups = [
        item for item in group_cards
        if item.get("pressure_level") in ("high", "medium")
    ][:10]

    stats = {
        "group_count": len(group_cards),
        "member_count": len(members),
        "task_count": len(tasks),
        "high_pressure_group_count": len([
            item for item in group_cards
            if item.get("pressure_level") == "high"
        ]),
        "medium_pressure_group_count": len([
            item for item in group_cards
            if item.get("pressure_level") == "medium"
        ]),
        "pending_task_count": sum(item.get("pending_tasks", 0) for item in group_cards),
        "abnormal_task_count": sum(item.get("abnormal_tasks", 0) for item in group_cards),
        "unassigned_group_count": len([
            item for item in group_cards
            if item.get("responsibility_status") == "unassigned"
        ]),
        "manual_mapping_count": len([
            item for item in group_cards
            if item.get("responsibility_status") == "manual"
        ]),
        "leader_pressure_count": len(leader_pressure),
    }

    decision = _build_decision(stats, high_pressure_groups)

    return {
        "summary": _build_summary(stats, decision),
        "stats": stats,
        "decision": decision,
        "group_cards": group_cards,
        "high_pressure_groups": high_pressure_groups,
        "leader_pressure": leader_pressure,
        "owner_pressure": owner_pressure,
        "mapping_logs": mapping_logs,
        "explain": (
            "V14 Phase A 按最新成员快照与 V12 任务反馈结果进行分组聚合。"
            "当前版本先按分组识别责任压力，后续再接入真实组长责任关系。"
        ),
    }


def _fetch_latest_members(
    conn,
) -> List[Dict[str, Any]]:
    columns = _get_columns(
        conn,
        "player_records",
    )

    if not columns:
        return []

    select_fields = [
        "member",
        "group_name",
        "av",
        "bs",
        "risk_level",
        "trend",
        "identity_score",
        "role_tag",
    ]

    available_fields = [
        field
        for field in select_fields
        if field in columns
    ]

    if "member" not in available_fields:
        return []

    if "group_name" not in available_fields:
        available_fields.append(
            "'' AS group_name"
        )

    clauses = []

    # player_records具备battle_id时，
    # 必须使用当前战场，禁止取全库最新时间。
    if "battle_id" in columns:
        current_row = conn.execute(
            """
            SELECT id
            FROM battles
            WHERE is_current = 1
            LIMIT 1
            """
        ).fetchone()

        if not current_row:
            return []

        try:
            current_battle_id = int(
                current_row[0]
            )
        except (
            TypeError,
            ValueError,
        ):
            return []

        clauses.append(
            f"battle_id = "
            f"{current_battle_id}"
        )

        if "snapshot_time" in columns:
            latest_deleted_filter = (
                "AND COALESCE("
                "is_deleted, 0"
                ") = 0"
                if "is_deleted" in columns
                else ""
            )

            clauses.append(
                "snapshot_time = ("
                "SELECT MAX(snapshot_time) "
                "FROM player_records "
                f"WHERE battle_id = "
                f"{current_battle_id} "
                f"{latest_deleted_filter}"
                ")"
            )

        elif "created_at" in columns:
            latest_deleted_filter = (
                "AND COALESCE("
                "is_deleted, 0"
                ") = 0"
                if "is_deleted" in columns
                else ""
            )

            clauses.append(
                "created_at = ("
                "SELECT MAX(created_at) "
                "FROM player_records "
                f"WHERE battle_id = "
                f"{current_battle_id} "
                f"{latest_deleted_filter}"
                ")"
            )

    elif "snapshot_time" in columns:
        latest_deleted_filter = (
            "WHERE COALESCE("
            "is_deleted, 0"
            ") = 0"
            if "is_deleted" in columns
            else ""
        )

        clauses.append(
            "snapshot_time = ("
            "SELECT MAX(snapshot_time) "
            "FROM player_records "
            f"{latest_deleted_filter}"
            ")"
        )

    elif "created_at" in columns:
        latest_deleted_filter = (
            "WHERE COALESCE("
            "is_deleted, 0"
            ") = 0"
            if "is_deleted" in columns
            else ""
        )

        clauses.append(
            "created_at = ("
            "SELECT MAX(created_at) "
            "FROM player_records "
            f"{latest_deleted_filter}"
            ")"
        )

    if "is_deleted" in columns:
        clauses.append(
            "COALESCE(is_deleted, 0) = 0"
        )

    where = ""

    if clauses:
        where = (
            "WHERE "
            + " AND ".join(clauses)
        )

    order_by = (
        "ORDER BY id"
        if "id" in columns
        else ""
    )

    sql = f"""
        SELECT {", ".join(available_fields)}
        FROM player_records
        {where}
        {order_by}
    """

    rows = _query_dicts(
        conn,
        sql,
    )

    # 同一战场同一快照如存在重复成员，
    # 按id顺序保留最后一条。
    dedup = {}

    for row in rows:
        member = str(
            row.get("member")
            or ""
        ).strip()

        if not member:
            continue

        dedup[member] = row

    return list(
        dedup.values()
    )



def _get_columns(conn, table: str) -> List[str]:
    try:
        rows = _query_dicts(conn, f"PRAGMA table_info({table})")
        return [row.get("name") for row in rows if row.get("name")]
    except Exception:
        return []


def _query_dicts(conn, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    cur = conn.execute(sql, params)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _build_member_map(members: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result = {}

    for row in members:
        member = str(row.get("member") or "").strip()
        if not member:
            continue
        result[member] = row

    return result


def _build_group_member_stats(members: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}

    for row in members:
        group_name = _clean_group_name(row.get("group_name"))
        stat = groups.setdefault(group_name, _new_group_stat(group_name))

        av = _to_float(row.get("av"))
        bs = _to_float(row.get("bs"))
        risk_level = str(row.get("risk_level") or "").strip()
        trend = str(row.get("trend") or "").strip()

        stat["member_count"] += 1
        stat["_av_total"] += av
        stat["_bs_total"] += bs

        if risk_level == "clear":
            stat["clear_count"] += 1
        elif risk_level == "danger":
            stat["danger_count"] += 1
        elif risk_level == "warning":
            stat["warning_count"] += 1
        elif risk_level == "protected":
            stat["protected_count"] += 1

        if av < 40 or bs < 50:
            stat["weak_member_count"] += 1

        if trend in ("down", "dead"):
            stat["down_trend_count"] += 1

        role_tag = str(row.get("role_tag") or "").strip()
        member_name = str(row.get("member") or "").strip()

        if member_name and role_tag == "leader":
            stat["leader_candidates"].append(member_name)
        elif member_name and role_tag == "admin":
            stat["admin_candidates"].append(member_name)

    return groups


def _new_group_stat(group_name: str) -> Dict[str, Any]:
    return {
        "group_name": group_name,
        "member_count": 0,
        "clear_count": 0,
        "danger_count": 0,
        "warning_count": 0,
        "protected_count": 0,
        "weak_member_count": 0,
        "down_trend_count": 0,
        "task_count": 0,
        "pending_tasks": 0,
        "done_tasks": 0,
        "abnormal_tasks": 0,
        "p1_tasks": 0,
        "leader_candidates": [],
        "admin_candidates": [],
        "_av_total": 0.0,
        "_bs_total": 0.0,
    }


def _merge_task_stats(
    group_stats: Dict[str, Dict[str, Any]],
    tasks: List[Dict[str, Any]],
    member_map: Dict[str, Dict[str, Any]],
) -> None:
    for task in tasks:
        target = str(task.get("target") or "").strip()
        priority = str(task.get("priority") or "").strip()
        status = str(task.get("feedback_status") or task.get("status") or "pending").strip()

        group_name = _resolve_task_group(target, member_map)
        stat = group_stats.setdefault(group_name, _new_group_stat(group_name))

        stat["task_count"] += 1

        if priority == "P1":
            stat["p1_tasks"] += 1

        if status == "pending":
            stat["pending_tasks"] += 1
        else:
            stat["done_tasks"] += 1

        if status in ("failed", "ignored"):
            stat["abnormal_tasks"] += 1


def _resolve_task_group(target: str, member_map: Dict[str, Dict[str, Any]]) -> str:
    if target in member_map:
        return _clean_group_name(member_map[target].get("group_name"))

    if not target:
        return "未识别任务"

    broad_targets = (
        "所有分组",
        "风险中心",
        "身份中心",
        "保护复核名单",
        "今日未反馈的清理候选",
        "主盟空位",
    )

    for key in broad_targets:
        if key in target:
            return "全盟任务"

    if "/" in target or "各分组" in target:
        return "全盟任务"

    return "未识别分组"


def _finalize_group_cards(
    group_stats: Dict[str, Dict[str, Any]],
    manual_mappings: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    cards = []

    for group_name, stat in group_stats.items():
        member_count = max(stat.get("member_count", 0), 1)

        avg_av = stat.get("_av_total", 0.0) / member_count
        avg_bs = stat.get("_bs_total", 0.0) / member_count

        feedback_rate = 0.0
        if stat.get("task_count", 0) > 0:
            feedback_rate = stat.get("done_tasks", 0) / stat.get("task_count", 1)

        pressure_score = _calc_pressure_score(stat, avg_av, avg_bs)
        pressure_level, pressure_label = _pressure_level(pressure_score)

        leader_info = _build_leader_info(
            stat,
            group_name,
            manual_mappings
        )

        card = {
            "group_name": group_name,
            "leader_display": leader_info.get("leader_display"),
            "leader_names": leader_info.get("leader_names"),
            "responsibility_status": leader_info.get("responsibility_status"),
            "responsibility_label": leader_info.get("responsibility_label"),
            "member_count": stat.get("member_count", 0),
            "avg_av": round(avg_av, 1),
            "avg_bs": round(avg_bs, 1),
            "clear_count": stat.get("clear_count", 0),
            "danger_count": stat.get("danger_count", 0),
            "warning_count": stat.get("warning_count", 0),
            "risk_member_count": (
                int(
                    stat.get("clear_count")
                    or 0
                )
                + int(
                    stat.get("danger_count")
                    or 0
                )
                + int(
                    stat.get("warning_count")
                    or 0
                )
            ),
            "protected_count": stat.get("protected_count", 0),
            "weak_member_count": stat.get("weak_member_count", 0),
            "down_trend_count": stat.get("down_trend_count", 0),
            "task_count": stat.get("task_count", 0),
            "pending_tasks": stat.get("pending_tasks", 0),
            "done_tasks": stat.get("done_tasks", 0),
            "abnormal_tasks": stat.get("abnormal_tasks", 0),
            "p1_tasks": stat.get("p1_tasks", 0),
            "feedback_rate": round(feedback_rate * 100, 1),
            "pressure_score": round(pressure_score, 1),
            "pressure_level": pressure_level,
            "pressure_label": pressure_label,
            "suggestion": _group_suggestion(stat, pressure_level),
        }

        cards.append(card)

    cards.sort(
        key=lambda x: (
            x.get("pressure_score", 0),
            x.get("pending_tasks", 0),
            x.get("danger_count", 0),
        ),
        reverse=True
    )

    return cards


def _build_leader_info(
    stat: Dict[str, Any],
    group_name: str,
    manual_mappings: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    manual = manual_mappings.get(group_name)

    if manual:
        leader_name = str(manual.get("leader_name") or "").strip()
        leader_role = str(manual.get("leader_role") or "组长").strip()
        note = str(manual.get("note") or "").strip()

        if leader_name:
            return {
                "leader_names": [leader_name],
                "leader_display": leader_name,
                "responsibility_status": "manual",
                "responsibility_label": f"手动指定：{leader_role}",
                "responsibility_note": note,
            }

    leaders = _unique_names(stat.get("leader_candidates", []))
    admins = _unique_names(stat.get("admin_candidates", []))

    if leaders:
        return {
            "leader_names": leaders,
            "leader_display": "、".join(leaders[:3]),
            "responsibility_status": "mapped",
            "responsibility_label": "自动识别组长",
            "responsibility_note": "",
        }

    if admins:
        return {
            "leader_names": admins,
            "leader_display": "、".join(admins[:3]),
            "responsibility_status": "admin_proxy",
            "responsibility_label": "管理代管",
            "responsibility_note": "",
        }

    return {
        "leader_names": [],
        "leader_display": "待指定",
        "responsibility_status": "unassigned",
        "responsibility_label": "待指定组长",
        "responsibility_note": "",
    }

def _unique_names(names: List[str]) -> List[str]:
    result = []
    seen = set()

    for name in names:
        clean = str(name or "").strip()
        if not clean or clean in seen:
            continue

        seen.add(clean)
        result.append(clean)

    return result


def _calc_pressure_score(stat: Dict[str, Any], avg_av: float, avg_bs: float) -> float:
    score = 0.0

    score += stat.get("danger_count", 0) * 4
    score += stat.get("warning_count", 0) * 2
    score += stat.get("weak_member_count", 0) * 1.5
    score += stat.get("down_trend_count", 0) * 1.5
    score += stat.get("pending_tasks", 0) * 2
    score += stat.get("abnormal_tasks", 0) * 3
    score += stat.get("p1_tasks", 0) * 1

    if avg_av < 40:
        score += 5

    if avg_bs < 50:
        score += 5

    return score


def _pressure_level(score: float) -> tuple[str, str]:
    if score >= 30:
        return "high", "高压"
    if score >= 15:
        return "medium", "关注"
    return "normal", "正常"


def _group_suggestion(stat: Dict[str, Any], pressure_level: str) -> str:
    if pressure_level == "high":
        return "建议盟主优先点名该组，要求组长确认风险成员与待反馈任务。"

    if stat.get("pending_tasks", 0) > 0:
        return "建议推动组长完成任务反馈，避免影响后续复盘。"

    if stat.get("danger_count", 0) > 0:
        return "建议复核该组风险成员，避免误清理保护对象。"

    return "当前分组压力可控，维持常规观察。"


def _build_leader_pressure(group_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    leaders: Dict[str, Dict[str, Any]] = {}

    for group in group_cards:
        owner = str(group.get("leader_display") or "待指定").strip()

        if not owner:
            owner = "待指定"

        status = str(group.get("responsibility_status") or "unassigned").strip()
        label = str(group.get("responsibility_label") or "").strip()

        item = leaders.setdefault(
            owner,
            {
                "owner": owner,
                "responsibility_status": status,
                "responsibility_label": label,
                "group_names": [],
                "group_count": 0,
                "high_group_count": 0,
                "medium_group_count": 0,
                "member_count": 0,
                "clear_count": 0,
                "danger_count": 0,
                "warning_count": 0,
                "risk_member_count": 0,
                "task_count": 0,
                "pending_tasks": 0,
                "done_tasks": 0,
                "abnormal_tasks": 0,
                "p1_tasks": 0,
                "pressure_score": 0.0,
            }
        )

        group_name = str(group.get("group_name") or "").strip()

        if group_name:
            item["group_names"].append(group_name)

        item["group_count"] += 1

        if group.get("pressure_level") == "high":
            item["high_group_count"] += 1
        elif group.get("pressure_level") == "medium":
            item["medium_group_count"] += 1

        item["member_count"] += int(group.get("member_count") or 0)
        item["clear_count"] += int(group.get("clear_count") or 0)
        item["danger_count"] += int(group.get("danger_count") or 0)
        item["warning_count"] += int(group.get("warning_count") or 0)
        item["risk_member_count"] += int(
            group.get("risk_member_count")
            or 0
        )
        item["task_count"] += int(group.get("task_count") or 0)
        item["pending_tasks"] += int(group.get("pending_tasks") or 0)
        item["done_tasks"] += int(group.get("done_tasks") or 0)
        item["abnormal_tasks"] += int(group.get("abnormal_tasks") or 0)
        item["p1_tasks"] += int(group.get("p1_tasks") or 0)
        item["pressure_score"] += float(group.get("pressure_score") or 0)

    result = []

    for item in leaders.values():
        task_count = max(item.get("task_count", 0), 1)
        item["feedback_rate"] = round(item.get("done_tasks", 0) / task_count * 100, 1)
        item["pressure_score"] = round(item.get("pressure_score", 0.0), 1)
        item["group_display"] = "、".join(item.get("group_names", [])[:5])

        if len(item.get("group_names", [])) > 5:
            item["group_display"] += f" 等{len(item.get('group_names', []))}组"

        item["suggestion"] = _leader_pressure_suggestion(item)

        result.append(item)

    result.sort(
        key=lambda x: (
            x.get("pressure_score", 0),
            x.get("high_group_count", 0),
            x.get("danger_count", 0),
            x.get("pending_tasks", 0),
        ),
        reverse=True
    )

    return result


def _leader_pressure_suggestion(item: Dict[str, Any]) -> str:
    if item.get("responsibility_status") == "unassigned":
        return "该分组尚未指定负责人，建议优先补齐责任人。"

    if item.get("high_group_count", 0) > 0:
        return "负责分组存在高压状态，建议盟主直接点名跟进风险复核。"

    if item.get("pending_tasks", 0) > 0:
        return "负责分组仍有待反馈任务，建议催促补齐执行反馈。"

    if item.get("abnormal_tasks", 0) > 0:
        return "负责分组存在异常反馈，建议复核是否执行失败或误判。"

    return "当前负责范围压力可控，维持常规跟进。"


def _build_owner_pressure(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    owners: Dict[str, Dict[str, Any]] = {}

    for task in tasks:
        owner = str(task.get("owner") or "未指定").strip()
        status = str(task.get("feedback_status") or task.get("status") or "pending").strip()
        priority = str(task.get("priority") or "").strip()

        stat = owners.setdefault(
            owner,
            {
                "owner": owner,
                "task_count": 0,
                "pending_tasks": 0,
                "done_tasks": 0,
                "abnormal_tasks": 0,
                "p1_tasks": 0,
            }
        )

        stat["task_count"] += 1

        if status == "pending":
            stat["pending_tasks"] += 1
        else:
            stat["done_tasks"] += 1

        if status in ("failed", "ignored"):
            stat["abnormal_tasks"] += 1

        if priority == "P1":
            stat["p1_tasks"] += 1

    result = []

    for stat in owners.values():
        task_count = max(stat.get("task_count", 0), 1)
        stat["feedback_rate"] = round(stat.get("done_tasks", 0) / task_count * 100, 1)
        stat["pressure_score"] = (
            stat.get("pending_tasks", 0) * 2
            + stat.get("abnormal_tasks", 0) * 3
            + stat.get("p1_tasks", 0)
        )
        result.append(stat)

    result.sort(key=lambda x: x.get("pressure_score", 0), reverse=True)
    return result


def _build_decision(
    stats: Dict[str, Any],
    high_pressure_groups: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if stats.get("high_pressure_group_count", 0) > 0:
        return {
            "label": "优先处理高压分组",
            "level": "warning",
            "confidence": 0.82,
            "reason": "当前存在高压分组，建议盟主优先推动组长反馈与风险复核。",
        }

    if stats.get("pending_task_count", 0) > 0:
        return {
            "label": "推动组长补齐反馈",
            "level": "info",
            "confidence": 0.76,
            "reason": "当前还有待反馈任务，建议先补齐执行反馈，再进入下一轮复盘。",
        }

    return {
        "label": "分组执行稳定",
        "level": "safe",
        "confidence": 0.7,
        "reason": "当前分组任务反馈较完整，暂无明显高压分组。",
    }


def _build_summary(stats: Dict[str, Any], decision: Dict[str, Any]) -> str:
    return (
        f"V14 组长协同驾驶舱已启动：当前识别 {stats.get('group_count', 0)} 个分组，"
        f"{stats.get('member_count', 0)} 名成员，关联任务 {stats.get('task_count', 0)} 项，"
        f"高压分组 {stats.get('high_pressure_group_count', 0)} 个，"
        f"待指定组长分组 {stats.get('unassigned_group_count', 0)} 个，"
        f"待反馈任务 {stats.get('pending_task_count', 0)} 项。"
        f"当前建议：{decision.get('label', '继续观察')}。"
    )


def _clean_group_name(value: Any) -> str:
    group_name = str(value or "").strip()

    if not group_name or group_name in ("None", "null", "-"):
        return "未分组"

    return group_name


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0
