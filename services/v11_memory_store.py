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
    conn.execute('\n        CREATE TABLE IF NOT EXISTS v11_strategy_snapshots (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            snapshot_key TEXT,\n            created_at TEXT,\n            selected_scenario TEXT,\n            selected_action TEXT,\n            confidence REAL,\n            total_members INTEGER,\n            raw_cleanup_count INTEGER,\n            shown_cleanup_count INTEGER,\n            shown_protection_count INTEGER,\n            raw_growth_count INTEGER,\n            management_pressure TEXT,\n            expected_risk_reduce INTEGER,\n            expected_management_cost INTEGER,\n            expected_stability_gain REAL,\n            expected_growth_gain REAL,\n            facts_json TEXT,\n            reasoning_stats_json TEXT,\n            simulation_json TEXT,\n            execution_json TEXT,\n            battle_id INTEGER,\n            FOREIGN KEY (battle_id)\n                REFERENCES battles(id)\n                ON UPDATE RESTRICT\n                ON DELETE RESTRICT\n        )\n    ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_p0s04_v11_strategy_snapshots_battle_lookup\n        ON v11_strategy_snapshots (\n            battle_id,\n            snapshot_key\n        )\n    ')
    conn.execute('\n        CREATE UNIQUE INDEX IF NOT EXISTS\n        uq_p0s04_v11_strategy_snapshots_scoped\n        ON v11_strategy_snapshots (\n            battle_id,\n            snapshot_key\n        )\n        WHERE battle_id IS NOT NULL\n    ')
    conn.execute('\n        CREATE UNIQUE INDEX IF NOT EXISTS\n        uq_p0s04_v11_strategy_snapshots_legacy_null\n        ON v11_strategy_snapshots (\n            snapshot_key\n        )\n        WHERE battle_id IS NULL\n    ')
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


def load_previous_v11_strategy_snapshot(conn, current_snapshot_key: str, *, battle_id: int) -> Optional[Dict[str, Any]]:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_v11_strategy_snapshot_table(conn)
    row = conn.execute('\n        SELECT *\n        FROM v11_strategy_snapshots\n        WHERE battle_id = ? AND snapshot_key != ?\n        ORDER BY id DESC\n        LIMIT 1\n    ', (battle_id, current_snapshot_key)).fetchone()
    if row is None:
        return None
    columns = ['id', 'snapshot_key', 'created_at', 'selected_scenario', 'selected_action', 'confidence', 'total_members', 'raw_cleanup_count', 'shown_cleanup_count', 'shown_protection_count', 'raw_growth_count', 'management_pressure', 'expected_risk_reduce', 'expected_management_cost', 'expected_stability_gain', 'expected_growth_gain', 'facts_json', 'reasoning_stats_json', 'simulation_json', 'execution_json']
    data = _row_to_dict(row, columns)
    for key in ['facts_json', 'reasoning_stats_json', 'simulation_json', 'execution_json']:
        if data.get(key):
            try:
                data[key.replace('_json', '')] = json.loads(data[key])
            except Exception:
                data[key.replace('_json', '')] = {}
    return data


def save_v11_strategy_snapshot(conn, report: Dict[str, Any], *, battle_id: int) -> str:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_v11_strategy_snapshot_table(conn)
    snapshot_key = build_current_v11_snapshot_key(report)
    reasoning = report.get('reasoning_report', {}) or {}
    reasoning_stats = reasoning.get('reasoning_stats', {}) or {}
    sim = report.get('v11_simulation_report', {}) or {}
    sim_facts = sim.get('facts', {}) or {}
    recommended = sim.get('recommended_scenario', {}) or {}
    decision = recommended.get('decision', {}) or {}
    expected = recommended.get('expected_result', {}) or {}
    execution = report.get('v11_execution_plan', {}) or {}
    params = {'battle_id': battle_id, 'snapshot_key': snapshot_key, 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'selected_scenario': recommended.get('name'), 'selected_action': decision.get('action'), 'confidence': decision.get('confidence'), 'total_members': _to_int(sim_facts.get('total_members')), 'raw_cleanup_count': _to_int(sim_facts.get('raw_cleanup_count')), 'shown_cleanup_count': _to_int(sim_facts.get('shown_cleanup_count')), 'shown_protection_count': _to_int(sim_facts.get('shown_protection_count')), 'raw_growth_count': _to_int(sim_facts.get('raw_growth_count')), 'management_pressure': sim_facts.get('management_pressure'), 'expected_risk_reduce': _to_int(expected.get('risk_reduce')), 'expected_management_cost': _to_int(expected.get('management_cost')), 'expected_stability_gain': _to_float(expected.get('stability_gain')), 'expected_growth_gain': _to_float(expected.get('growth_gain')), 'facts_json': _json(sim_facts), 'reasoning_stats_json': _json(reasoning_stats), 'simulation_json': _json(sim), 'execution_json': _json(execution)}
    conn.execute('\n        INSERT OR IGNORE INTO v11_strategy_snapshots (\n            battle_id,\n            snapshot_key,\n            created_at,\n            selected_scenario,\n            selected_action,\n            confidence,\n            total_members,\n            raw_cleanup_count,\n            shown_cleanup_count,\n            shown_protection_count,\n            raw_growth_count,\n            management_pressure,\n            expected_risk_reduce,\n            expected_management_cost,\n            expected_stability_gain,\n            expected_growth_gain,\n            facts_json,\n            reasoning_stats_json,\n            simulation_json,\n            execution_json\n        )\n        VALUES (\n            :battle_id,\n            :snapshot_key,\n            :created_at,\n            :selected_scenario,\n            :selected_action,\n            :confidence,\n            :total_members,\n            :raw_cleanup_count,\n            :shown_cleanup_count,\n            :shown_protection_count,\n            :raw_growth_count,\n            :management_pressure,\n            :expected_risk_reduce,\n            :expected_management_cost,\n            :expected_stability_gain,\n            :expected_growth_gain,\n            :facts_json,\n            :reasoning_stats_json,\n            :simulation_json,\n            :execution_json\n        )\n    ', params)
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
    conn.execute('\n        CREATE TABLE IF NOT EXISTS v11_reflection_records (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            snapshot_key TEXT,\n            created_at TEXT,\n            status TEXT,\n            decision_action TEXT,\n            decision_label TEXT,\n            confidence REAL,\n            selected_scenario TEXT,\n            selected_action TEXT,\n            expected_risk_reduce INTEGER,\n            actual_risk_reduce INTEGER,\n            risk_delta INTEGER,\n            cleanup_task_delta INTEGER,\n            growth_delta INTEGER,\n            metrics_json TEXT,\n            reflection_json TEXT,\n            battle_id INTEGER,\n            FOREIGN KEY (battle_id)\n                REFERENCES battles(id)\n                ON UPDATE RESTRICT\n                ON DELETE RESTRICT\n        )\n    ')
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_p0s04_v11_reflection_records_battle_lookup\n        ON v11_reflection_records (\n            battle_id,\n            snapshot_key\n        )\n    ')
    conn.execute('\n        CREATE UNIQUE INDEX IF NOT EXISTS\n        uq_p0s04_v11_reflection_records_scoped\n        ON v11_reflection_records (\n            battle_id,\n            snapshot_key\n        )\n        WHERE battle_id IS NOT NULL\n    ')
    conn.execute('\n        CREATE UNIQUE INDEX IF NOT EXISTS\n        uq_p0s04_v11_reflection_records_legacy_null\n        ON v11_reflection_records (\n            snapshot_key\n        )\n        WHERE battle_id IS NULL\n    ')
    conn.commit()


def save_v11_reflection_record(conn, snapshot_key: str, report: Dict[str, Any], *, battle_id: int) -> None:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_v11_reflection_records_table(conn)
    ref = report.get('v11_reflection_report', {}) or {}
    metrics = ref.get('metrics', {}) or {}
    decision = ref.get('decision', {}) or {}
    sim = report.get('v11_simulation_report', {}) or {}
    recommended = sim.get('recommended_scenario', {}) or {}
    sim_decision = recommended.get('decision', {}) or {}
    params = {'battle_id': battle_id, 'snapshot_key': snapshot_key, 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'status': ref.get('status'), 'decision_action': decision.get('action'), 'decision_label': decision.get('label'), 'confidence': decision.get('confidence'), 'selected_scenario': recommended.get('name'), 'selected_action': sim_decision.get('action'), 'expected_risk_reduce': _to_int(metrics.get('expected_risk_reduce')), 'actual_risk_reduce': _to_int(metrics.get('actual_risk_reduce')), 'risk_delta': _to_int(metrics.get('risk_delta')), 'cleanup_task_delta': _to_int(metrics.get('cleanup_task_delta')), 'growth_delta': _to_int(metrics.get('growth_delta')), 'metrics_json': _json(metrics), 'reflection_json': _json(ref)}
    conn.execute('\n        INSERT OR IGNORE INTO v11_reflection_records (\n            battle_id,\n            snapshot_key,\n            created_at,\n            status,\n            decision_action,\n            decision_label,\n            confidence,\n            selected_scenario,\n            selected_action,\n            expected_risk_reduce,\n            actual_risk_reduce,\n            risk_delta,\n            cleanup_task_delta,\n            growth_delta,\n            metrics_json,\n            reflection_json\n        )\n        VALUES (\n            :battle_id,\n            :snapshot_key,\n            :created_at,\n            :status,\n            :decision_action,\n            :decision_label,\n            :confidence,\n            :selected_scenario,\n            :selected_action,\n            :expected_risk_reduce,\n            :actual_risk_reduce,\n            :risk_delta,\n            :cleanup_task_delta,\n            :growth_delta,\n            :metrics_json,\n            :reflection_json\n        )\n    ', params)
    conn.commit()


def load_v11_reflection_history(conn, limit: int=20, *, battle_id: int) -> list[Dict[str, Any]]:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_v11_reflection_records_table(conn)
    cursor = conn.execute('\n        SELECT *\n        FROM v11_reflection_records\n        \n        WHERE battle_id = ?\n        ORDER BY id DESC\n        LIMIT ?\n    ', (battle_id, limit))
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    result = []
    for row in rows:
        data = _row_to_dict(row, columns)
        for key in ['metrics_json', 'reflection_json']:
            if data.get(key):
                try:
                    data[key.replace('_json', '')] = json.loads(data[key])
                except Exception:
                    data[key.replace('_json', '')] = {}
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
