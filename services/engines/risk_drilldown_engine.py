from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_risk_drilldown_report(
    conn,
    group_names: Optional[List[str]] = None,
    limit_per_group: int = 8,
    global_limit: int = 80,
    battle_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    V15 风险人员穿透引擎。

    关键原则：
    1. 只取当前战场最新快照；
    2. 按 member 去重；
    3. 纳入 clear、danger、warning；
    4. 只读展示，不写数据库。
    """

    resolved_battle_id = _resolve_battle_id(
        conn,
        battle_id,
    )

    if resolved_battle_id is None:
        return {
            "battle_id": None,
            "latest_snapshot_time": "",
            "total_risk_members": 0,
            "clear_count": 0,
            "danger_count": 0,
            "warning_count": 0,
            "by_group": {},
            "by_group_counts": {},
            "by_group_level_counts": {},
            "top_members": [],
            "summary": "当前未设置战场，暂无风险数据。",
        }

    rows = _load_latest_risk_members(
        conn,
        resolved_battle_id,
    )

    if group_names:
        group_set = {
            str(name or "").strip()
            for name in group_names
            if str(name or "").strip()
        }

        rows = [
            item
            for item in rows
            if item.get("group_name")
            in group_set
        ]

    full_by_group: Dict[
        str,
        List[Dict[str, Any]],
    ] = {}

    for item in rows:
        group_name = str(
            item.get("group_name")
            or ""
        ).strip()

        if not group_name:
            continue

        full_by_group.setdefault(
            group_name,
            [],
        ).append(item)

    by_group_counts = {
        group_name: len(items)
        for group_name, items
        in full_by_group.items()
    }

    by_group_level_counts = {}

    for group_name, items in (
        full_by_group.items()
    ):
        by_group_level_counts[group_name] = {
            "clear": sum(
                item.get("risk_level")
                == "clear"
                for item in items
            ),
            "danger": sum(
                item.get("risk_level")
                == "danger"
                for item in items
            ),
            "warning": sum(
                item.get("risk_level")
                == "warning"
                for item in items
            ),
        }

    preview_limit = max(
        int(limit_per_group or 0),
        0,
    )

    by_group = {
        group_name: items[:preview_limit]
        for group_name, items
        in full_by_group.items()
    }

    top_limit = max(
        int(global_limit or 0),
        0,
    )

    return {
        "battle_id": resolved_battle_id,
        "latest_snapshot_time": (
            _get_latest_snapshot_time(
                conn,
                resolved_battle_id,
            )
        ),
        "total_risk_members": len(rows),
        "clear_count": sum(
            item.get("risk_level")
            == "clear"
            for item in rows
        ),
        "danger_count": sum(
            item.get("risk_level")
            == "danger"
            for item in rows
        ),
        "warning_count": sum(
            item.get("risk_level")
            == "warning"
            for item in rows
        ),
        "by_group": by_group,
        "by_group_counts": by_group_counts,
        "by_group_level_counts": (
            by_group_level_counts
        ),
        "top_members": rows[:top_limit],
        "summary": _build_summary(rows),
    }



def attach_risk_members_to_groups(
    groups: List[Dict[str, Any]],
    risk_report: Dict[str, Any],
    limit_per_group: int = 5,
) -> List[Dict[str, Any]]:
    by_group = (
        risk_report.get("by_group", {})
        or {}
    )

    by_group_counts = (
        risk_report.get(
            "by_group_counts",
            {},
        )
        or {}
    )

    level_counts = (
        risk_report.get(
            "by_group_level_counts",
            {},
        )
        or {}
    )

    preview_limit = max(
        int(limit_per_group or 0),
        0,
    )

    for group in groups or []:
        group_name = str(
            group.get("group_name")
            or ""
        ).strip()

        preview_members = (
            by_group.get(group_name, [])
            or []
        )[:preview_limit]

        group_levels = (
            level_counts.get(
                group_name,
                {},
            )
            or {}
        )

        group["risk_members"] = (
            preview_members
        )

        # 总人数使用完整集合，不再被TOP预览截断。
        group["risk_member_count"] = int(
            by_group_counts.get(
                group_name,
                len(preview_members),
            )
            or 0
        )

        group["risk_clear_count"] = int(
            group_levels.get(
                "clear",
                0,
            )
            or 0
        )

        group["risk_danger_count"] = int(
            group_levels.get(
                "danger",
                0,
            )
            or 0
        )

        group["risk_warning_count"] = int(
            group_levels.get(
                "warning",
                0,
            )
            or 0
        )

    return groups



def _resolve_battle_id(
    conn,
    battle_id: Optional[int] = None,
) -> Optional[int]:
    if battle_id is not None:
        try:
            return int(battle_id)
        except (TypeError, ValueError):
            return None

    row = conn.execute(
        """
        SELECT id
        FROM battles
        WHERE is_current = 1
        LIMIT 1
        """
    ).fetchone()

    if not row:
        return None

    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _load_latest_risk_members(
    conn,
    battle_id: int,
) -> List[Dict[str, Any]]:
    cur = conn.execute(
        """
        WITH latest AS (
            SELECT
                MAX(snapshot_time)
                    AS snapshot_time
            FROM player_records
            WHERE battle_id = ?
              AND COALESCE(
                  is_deleted,
                  0
              ) = 0
        ),
        latest_rows AS (
            SELECT p.*
            FROM player_records AS p
            JOIN latest AS l
              ON p.snapshot_time
               = l.snapshot_time
            WHERE p.battle_id = ?
              AND COALESCE(
                  p.is_deleted,
                  0
              ) = 0
              AND COALESCE(
                  p.member,
                  ''
              ) != ''
              AND COALESCE(
                  p.group_name,
                  ''
              ) != ''
        ),
        dedup AS (
            SELECT lr.*
            FROM latest_rows AS lr
            JOIN (
                SELECT
                    member,
                    MAX(id) AS max_id
                FROM latest_rows
                GROUP BY member
            ) AS x
              ON lr.member = x.member
             AND lr.id = x.max_id
        )
        SELECT
            TRIM(group_name)
                AS group_name,
            member,
            risk_level,
            COALESCE(
                risk_reason,
                ''
            ) AS risk_reason,
            ROUND(
                COALESCE(av, 0),
                1
            ) AS av,
            ROUND(
                COALESCE(bs, 0),
                1
            ) AS bs,
            COALESCE(
                trend,
                'stable'
            ) AS trend,
            COALESCE(
                identity_score,
                0
            ) AS identity_score,
            COALESCE(
                is_protected,
                0
            ) AS is_protected,
            COALESCE(
                stall_count,
                0
            ) AS stall_count,
            COALESCE(wv, 0) AS wv,
            COALESCE(bv, 0) AS bv
        FROM dedup
        WHERE risk_level IN (
            'clear',
            'danger',
            'warning'
        )
        ORDER BY
            CASE risk_level
                WHEN 'clear' THEN 1
                WHEN 'danger' THEN 2
                WHEN 'warning' THEN 3
                ELSE 4
            END,
            av ASC,
            bs ASC,
            identity_score DESC,
            member
        """,
        (
            battle_id,
            battle_id,
        ),
    )

    cols = [
        desc[0]
        for desc in cur.description
    ]

    rows = []

    for row in cur.fetchall():
        item = dict(
            zip(cols, row)
        )

        item["risk_label"] = (
            _risk_label(
                item.get("risk_level")
            )
        )

        item["trend_label"] = (
            _trend_label(
                item.get("trend")
            )
        )

        item["suggest_action"] = (
            _suggest_action(item)
        )

        rows.append(item)

    return rows



def _get_latest_snapshot_time(
    conn,
    battle_id: Optional[int] = None,
) -> str:
    resolved_battle_id = _resolve_battle_id(
        conn,
        battle_id,
    )

    if resolved_battle_id is None:
        return ""

    row = conn.execute(
        """
        SELECT MAX(snapshot_time)
        FROM player_records
        WHERE battle_id = ?
          AND COALESCE(
              is_deleted,
              0
          ) = 0
        """,
        (resolved_battle_id,),
    ).fetchone()

    if not row:
        return ""

    return str(row[0] or "")



def _risk_label(level: Any) -> str:
    level = str(level or "").strip()

    labels = {
        "danger": "危险",
        "warning": "预警",
        "safe": "安全",
        "protected": "保护",
        "clear": "建议清理",
    }

    return labels.get(level, level or "未知")


def _trend_label(trend: Any) -> str:
    trend = str(trend or "").strip()

    labels = {
        "explosive": "高速成长",
        "up": "上升",
        "stable": "稳定",
        "down": "下滑",
        "dead": "停滞",
    }

    return labels.get(trend, trend or "未知")


def _suggest_action(
    item: Dict[str, Any],
) -> str:
    risk_level = str(
        item.get("risk_level")
        or ""
    )

    reason = str(
        item.get("risk_reason")
        or ""
    )

    av = float(
        item.get("av")
        or 0
    )

    bs = float(
        item.get("bs")
        or 0
    )

    is_protected = int(
        item.get("is_protected")
        or 0
    )

    if is_protected:
        return "已保护，建议复核保护理由"

    if risk_level == "clear":
        return "建议清理，先进行人工复核"

    if (
        risk_level == "danger"
        and av < 10
        and bs < 25
    ):
        return "优先确认是否清理"

    if (
        "连续停滞" in reason
        or "长期低贡献" in reason
    ):
        return "要求组长二次确认"

    if "活跃不足" in reason:
        return "联系确认是否回归"

    if risk_level == "warning":
        return "观察一轮后复核"

    return "组长确认后处理"



def _build_summary(
    rows: List[Dict[str, Any]],
) -> str:
    clear = sum(
        item.get("risk_level")
        == "clear"
        for item in rows
    )

    danger = sum(
        item.get("risk_level")
        == "danger"
        for item in rows
    )

    warning = sum(
        item.get("risk_level")
        == "warning"
        for item in rows
    )

    return (
        f"当前战场最新快照识别异常成员 "
        f"{len(rows)} 人，"
        f"其中建议清理 {clear} 人，"
        f"危险 {danger} 人，"
        f"预警 {warning} 人。"
    )



def build_group_risk_detail_report(
    conn,
    group_name: str,
    battle_id: Optional[int] = None,
) -> Dict[str, Any]:
    group_name = str(
        group_name
        or ""
    ).strip()

    risk_report = (
        build_risk_drilldown_report(
            conn,
            group_names=[group_name],
            limit_per_group=999,
            global_limit=999,
            battle_id=battle_id,
        )
    )

    members = (
        risk_report
        .get("by_group", {})
        .get(group_name, [])
        or []
    )

    clear_members = [
        item
        for item in members
        if item.get("risk_level")
        == "clear"
    ]

    danger_members = [
        item
        for item in members
        if item.get("risk_level")
        == "danger"
    ]

    warning_members = [
        item
        for item in members
        if item.get("risk_level")
        == "warning"
    ]

    decision = (
        _build_group_risk_decision(
            group_name,
            members,
            clear_members,
            danger_members,
            warning_members,
        )
    )

    return {
        "battle_id": (
            risk_report.get("battle_id")
        ),
        "group_name": group_name,
        "latest_snapshot_time": (
            risk_report.get(
                "latest_snapshot_time",
                "",
            )
        ),
        "members": members,
        "clear_members": clear_members,
        "danger_members": danger_members,
        "warning_members": warning_members,
        "stats": {
            "total": len(members),
            "clear": len(clear_members),
            "danger": len(danger_members),
            "warning": len(
                warning_members
            ),
        },
        "decision": decision,
        "summary": (
            f"分组「{group_name}」当前异常成员 "
            f"{len(members)} 人，"
            f"其中建议清理 "
            f"{len(clear_members)} 人，"
            f"危险 {len(danger_members)} 人，"
            f"预警 {len(warning_members)} 人。"
        ),
    }



def _build_group_risk_decision(
    group_name: str,
    members: List[Dict[str, Any]],
    clear_members: List[Dict[str, Any]],
    danger_members: List[Dict[str, Any]],
    warning_members: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if len(clear_members) >= 8:
        return {
            "level": "danger",
            "label": "优先复核建议清理成员",
            "reason": (
                f"{group_name} 建议清理成员较多，"
                "应要求负责人逐个核实，"
                "避免直接批量处理。"
            ),
        }

    if len(danger_members) >= 8:
        return {
            "level": "danger",
            "label": "优先处理危险成员",
            "reason": (
                f"{group_name} 危险成员较多，"
                "应要求负责人逐个确认是否清理、"
                "保护或继续观察。"
            ),
        }

    if clear_members:
        return {
            "level": "warning",
            "label": "先复核建议清理成员",
            "reason": (
                f"{group_name} 存在建议清理成员，"
                "应先人工复核，再决定是否处理。"
            ),
        }

    if danger_members:
        return {
            "level": "warning",
            "label": "先处理危险成员",
            "reason": (
                f"{group_name} 存在危险成员，"
                "应先处理危险成员，"
                "再观察预警成员。"
            ),
        }

    if warning_members:
        return {
            "level": "info",
            "label": "观察预警成员",
            "reason": (
                f"{group_name} 暂无清理或危险成员，"
                "但存在预警成员，"
                "建议下一轮快照后复核。"
            ),
        }

    return {
        "level": "safe",
        "label": "暂无异常成员",
        "reason": (
            f"{group_name} 当前没有异常成员。"
        ),
    }

