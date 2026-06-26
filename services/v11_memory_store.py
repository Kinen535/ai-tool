from __future__ import annotations

"""
V11 Memory Store

职责：
1. 保存 V11 推理 / 推演 / 执行计划快照。
2. 读取上一轮 V11 快照，供 Reflection Engine 复盘。
3. 只做数据库 I/O，不做业务决策。
4. 不属于 Engine，不参与规则判断。
"""

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional


def ensure_v11_strategy_snapshot_table(conn) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS v11_strategy_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_key TEXT UNIQUE,
        created_at TEXT,

        selected_scenario TEXT,
        selected_action TEXT,
        confidence REAL,

        total_members INTEGER,
        raw_cleanup_count INTEGER,
        shown_cleanup_count INTEGER,
        shown_protection_count INTEGER,
        raw_growth_count INTEGER,
        management_pressure TEXT,

        expected_risk_reduce INTEGER,
        expected_management_cost INTEGER,
        expected_stability_gain REAL,
        expected_growth_gain REAL,

        facts_json TEXT,
        reasoning_stats_json TEXT,
        simulation_json TEXT,
        execution_json TEXT
    )
    """)
    conn.commit()


def build_current_v11_snapshot_key(report: Dict[str, Any]) -> str:
    sim = report.get("v11_simulation_report", {}) or {}
    facts = sim.get("facts", {}) or {}
    recommended = sim.get("recommended_scenario", {}) or {}

    decision = recommended.get("decision", {}) or {}

    raw = "|".join([
        str(facts.get("total_members", "")),
        str(facts.get("raw_cleanup_count", "")),
        str(facts.get("shown_cleanup_count", "")),
        str(facts.get("shown_protection_count", "")),
        str(facts.get("raw_growth_count", "")),
        str(facts.get("management_pressure", "")),
        str(recommended.get("name", "")),
        str(decision.get("action", "")),
    ])

    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def load_previous_v11_strategy_snapshot(
    conn,
    current_snapshot_key: str,
) -> Optional[Dict[str, Any]]:
    ensure_v11_strategy_snapshot_table(conn)

    row = conn.execute("""
        SELECT *
        FROM v11_strategy_snapshots
        WHERE snapshot_key != ?
        ORDER BY id DESC
        LIMIT 1
    """, (current_snapshot_key,)).fetchone()

    if row is None:
        return None

    # 兼容 sqlite3.Row 和普通 tuple
    columns = [
        "id",
        "snapshot_key",
        "created_at",
        "selected_scenario",
        "selected_action",
        "confidence",
        "total_members",
        "raw_cleanup_count",
        "shown_cleanup_count",
        "shown_protection_count",
        "raw_growth_count",
        "management_pressure",
        "expected_risk_reduce",
        "expected_management_cost",
        "expected_stability_gain",
        "expected_growth_gain",
        "facts_json",
        "reasoning_stats_json",
        "simulation_json",
        "execution_json",
    ]

    data = _row_to_dict(row, columns)

    for key in [
        "facts_json",
        "reasoning_stats_json",
        "simulation_json",
        "execution_json",
    ]:
        if data.get(key):
            try:
                data[key.replace("_json", "")] = json.loads(data[key])
            except Exception:
                data[key.replace("_json", "")] = {}

    return data


def save_v11_strategy_snapshot(
    conn,
    report: Dict[str, Any],
) -> str:
    ensure_v11_strategy_snapshot_table(conn)

    snapshot_key = build_current_v11_snapshot_key(report)

    reasoning = report.get("reasoning_report", {}) or {}
    reasoning_stats = reasoning.get("reasoning_stats", {}) or {}

    sim = report.get("v11_simulation_report", {}) or {}
    sim_facts = sim.get("facts", {}) or {}
    recommended = sim.get("recommended_scenario", {}) or {}
    decision = recommended.get("decision", {}) or {}
    expected = recommended.get("expected_result", {}) or {}

    execution = report.get("v11_execution_plan", {}) or {}

    params = {
        "snapshot_key": snapshot_key,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

        "selected_scenario": recommended.get("name"),
        "selected_action": decision.get("action"),
        "confidence": decision.get("confidence"),

        "total_members": _to_int(sim_facts.get("total_members")),
        "raw_cleanup_count": _to_int(sim_facts.get("raw_cleanup_count")),
        "shown_cleanup_count": _to_int(sim_facts.get("shown_cleanup_count")),
        "shown_protection_count": _to_int(sim_facts.get("shown_protection_count")),
        "raw_growth_count": _to_int(sim_facts.get("raw_growth_count")),
        "management_pressure": sim_facts.get("management_pressure"),

        "expected_risk_reduce": _to_int(expected.get("risk_reduce")),
        "expected_management_cost": _to_int(expected.get("management_cost")),
        "expected_stability_gain": _to_float(expected.get("stability_gain")),
        "expected_growth_gain": _to_float(expected.get("growth_gain")),

        "facts_json": _json(sim_facts),
        "reasoning_stats_json": _json(reasoning_stats),
        "simulation_json": _json(sim),
        "execution_json": _json(execution),
    }

    conn.execute("""
        INSERT OR IGNORE INTO v11_strategy_snapshots (
            snapshot_key,
            created_at,
            selected_scenario,
            selected_action,
            confidence,
            total_members,
            raw_cleanup_count,
            shown_cleanup_count,
            shown_protection_count,
            raw_growth_count,
            management_pressure,
            expected_risk_reduce,
            expected_management_cost,
            expected_stability_gain,
            expected_growth_gain,
            facts_json,
            reasoning_stats_json,
            simulation_json,
            execution_json
        )
        VALUES (
            :snapshot_key,
            :created_at,
            :selected_scenario,
            :selected_action,
            :confidence,
            :total_members,
            :raw_cleanup_count,
            :shown_cleanup_count,
            :shown_protection_count,
            :raw_growth_count,
            :management_pressure,
            :expected_risk_reduce,
            :expected_management_cost,
            :expected_stability_gain,
            :expected_growth_gain,
            :facts_json,
            :reasoning_stats_json,
            :simulation_json,
            :execution_json
        )
    """, params)

    conn.commit()

    return snapshot_key


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def ensure_v11_reflection_records_table(conn) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS v11_reflection_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_key TEXT UNIQUE,
        created_at TEXT,

        status TEXT,
        decision_action TEXT,
        decision_label TEXT,
        confidence REAL,

        selected_scenario TEXT,
        selected_action TEXT,

        expected_risk_reduce INTEGER,
        actual_risk_reduce INTEGER,
        risk_delta INTEGER,
        cleanup_task_delta INTEGER,
        growth_delta INTEGER,

        metrics_json TEXT,
        reflection_json TEXT
    )
    """)
    conn.commit()


def save_v11_reflection_record(
    conn,
    snapshot_key: str,
    report: Dict[str, Any],
) -> None:
    ensure_v11_reflection_records_table(conn)

    ref = report.get("v11_reflection_report", {}) or {}
    metrics = ref.get("metrics", {}) or {}
    decision = ref.get("decision", {}) or {}

    sim = report.get("v11_simulation_report", {}) or {}
    recommended = sim.get("recommended_scenario", {}) or {}
    sim_decision = recommended.get("decision", {}) or {}

    params = {
        "snapshot_key": snapshot_key,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

        "status": ref.get("status"),
        "decision_action": decision.get("action"),
        "decision_label": decision.get("label"),
        "confidence": decision.get("confidence"),

        "selected_scenario": recommended.get("name"),
        "selected_action": sim_decision.get("action"),

        "expected_risk_reduce": _to_int(metrics.get("expected_risk_reduce")),
        "actual_risk_reduce": _to_int(metrics.get("actual_risk_reduce")),
        "risk_delta": _to_int(metrics.get("risk_delta")),
        "cleanup_task_delta": _to_int(metrics.get("cleanup_task_delta")),
        "growth_delta": _to_int(metrics.get("growth_delta")),

        "metrics_json": _json(metrics),
        "reflection_json": _json(ref),
    }

    conn.execute("""
        INSERT OR IGNORE INTO v11_reflection_records (
            snapshot_key,
            created_at,
            status,
            decision_action,
            decision_label,
            confidence,
            selected_scenario,
            selected_action,
            expected_risk_reduce,
            actual_risk_reduce,
            risk_delta,
            cleanup_task_delta,
            growth_delta,
            metrics_json,
            reflection_json
        )
        VALUES (
            :snapshot_key,
            :created_at,
            :status,
            :decision_action,
            :decision_label,
            :confidence,
            :selected_scenario,
            :selected_action,
            :expected_risk_reduce,
            :actual_risk_reduce,
            :risk_delta,
            :cleanup_task_delta,
            :growth_delta,
            :metrics_json,
            :reflection_json
        )
    """, params)

    conn.commit()


def load_v11_reflection_history(
    conn,
    limit: int = 20,
) -> list[Dict[str, Any]]:
    ensure_v11_reflection_records_table(conn)

    cursor = conn.execute("""
        SELECT *
        FROM v11_reflection_records
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    result = []

    for row in rows:
        data = _row_to_dict(row, columns)

        for key in ["metrics_json", "reflection_json"]:
            if data.get(key):
                try:
                    data[key.replace("_json", "")] = json.loads(data[key])
                except Exception:
                    data[key.replace("_json", "")] = {}

        result.append(data)

    return result


def _row_to_dict(row: Any, columns: list[str] | None = None) -> Dict[str, Any]:
    """
    兼容 sqlite3.Row 和普通 tuple。
    app.py 中的 conn 不一定设置 row_factory，所以不能直接 dict(row)。
    """
    if row is None:
        return {}

    if hasattr(row, "keys"):
        return dict(row)

    if columns:
        return dict(zip(columns, row))

    return {}
