from __future__ import annotations

"""
V12 - Feedback Store

职责：
1. 保存 V12 执行反馈记录。
2. 读取指定 V11/V12 快照下的任务反馈。
3. 只做数据库 I/O，不做业务判断。
4. 不属于 Engine，不参与规则决策。
"""

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional


def ensure_v12_execution_feedback_table(conn) -> None:
    conn.execute("\n        CREATE TABLE IF NOT EXISTS v12_execution_feedback (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            snapshot_key TEXT,\n            task_key TEXT,\n            phase TEXT,\n            priority TEXT,\n            task_title TEXT,\n            target TEXT,\n            owner TEXT,\n            status TEXT DEFAULT 'pending',\n            feedback_note TEXT DEFAULT '',\n            created_at TEXT,\n            updated_at TEXT,\n            battle_id INTEGER,\n            FOREIGN KEY (battle_id)\n                REFERENCES battles(id)\n                ON UPDATE RESTRICT\n                ON DELETE RESTRICT\n        )\n    ")
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_p0s04_v12_execution_feedback_battle_lookup\n        ON v12_execution_feedback (\n            battle_id,\n            snapshot_key,\n            task_key\n        )\n    ')
    conn.execute('\n        CREATE UNIQUE INDEX IF NOT EXISTS\n        uq_p0s04_v12_execution_feedback_scoped\n        ON v12_execution_feedback (\n            battle_id,\n            snapshot_key,\n            task_key\n        )\n        WHERE battle_id IS NOT NULL\n    ')
    conn.execute('\n        CREATE UNIQUE INDEX IF NOT EXISTS\n        uq_p0s04_v12_execution_feedback_legacy_null\n        ON v12_execution_feedback (\n            snapshot_key,\n            task_key\n        )\n        WHERE battle_id IS NULL\n    ')
    conn.commit()


def build_task_key(task: Dict[str, Any]) -> str:
    """
    根据执行任务生成稳定 task_key。
    不依赖数据库自增 id，方便后续快照与页面任务对应。
    """
    raw = "|".join([
        str(task.get("phase", "")),
        str(task.get("priority", "")),
        str(task.get("title", "")),
        str(task.get("target", "")),
        str(task.get("owner", "")),
    ])

    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def load_execution_feedback_records(conn, snapshot_key: str, *, battle_id: int) -> List[Dict[str, Any]]:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_v12_execution_feedback_table(conn)
    cursor = conn.execute('\n        SELECT *\n        FROM v12_execution_feedback\n        WHERE battle_id = ? AND snapshot_key = ?\n        ORDER BY id ASC\n    ', (battle_id, snapshot_key))
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    return [_row_to_dict(row, columns) for row in rows]


def get_feedback_map(
    feedback_records: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    return {
        item.get("task_key"): item
        for item in feedback_records
        if item.get("task_key")
    }


def save_execution_feedback(conn, snapshot_key: str, task: Dict[str, Any], status: str, feedback_note: str='', *, battle_id: int) -> str:
    """
    保存单条任务反馈。

    V12 Phase F：
    每次状态变化都会写入 v12_feedback_logs，形成审计轨迹。
    """
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_v12_execution_feedback_table(conn)
    ensure_v12_feedback_logs_table(conn)
    task_key = build_task_key(task)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_status = status or 'pending'
    old_row = conn.execute('\n        SELECT status\n        FROM v12_execution_feedback\n        WHERE battle_id = ? AND snapshot_key = ?\n          AND task_key = ?\n        LIMIT 1\n    ', (battle_id, snapshot_key, task_key)).fetchone()
    old_status = _first_value(old_row) or 'pending'
    params = {'battle_id': battle_id, 'snapshot_key': snapshot_key, 'task_key': task_key, 'phase': task.get('phase'), 'priority': task.get('priority'), 'task_title': task.get('title'), 'target': task.get('target'), 'owner': task.get('owner'), 'status': new_status, 'feedback_note': feedback_note or '', 'created_at': now, 'updated_at': now}
    conn.execute('\n        INSERT INTO v12_execution_feedback (\n            battle_id,\n            snapshot_key,\n            task_key,\n            phase,\n            priority,\n            task_title,\n            target,\n            owner,\n            status,\n            feedback_note,\n            created_at,\n            updated_at\n        )\n        VALUES (\n            :battle_id,\n            :snapshot_key,\n            :task_key,\n            :phase,\n            :priority,\n            :task_title,\n            :target,\n            :owner,\n            :status,\n            :feedback_note,\n            :created_at,\n            :updated_at\n        )\n        ON CONFLICT(battle_id, snapshot_key, task_key) WHERE battle_id IS NOT NULL\n        DO UPDATE SET\n            status = excluded.status,\n            feedback_note = excluded.feedback_note,\n            updated_at = excluded.updated_at\n    ', params)
    if old_status != new_status or feedback_note:
        conn.execute('\n            INSERT INTO v12_feedback_logs (\n            battle_id,\n                snapshot_key,\n                task_key,\n                phase,\n                priority,\n                task_title,\n                target,\n                owner,\n                old_status,\n                new_status,\n                feedback_note,\n                created_at\n            )\n            VALUES (\n            :battle_id,\n                :snapshot_key,\n                :task_key,\n                :phase,\n                :priority,\n                :task_title,\n                :target,\n                :owner,\n                :old_status,\n                :new_status,\n                :feedback_note,\n                :created_at\n            )\n        ', {'battle_id': battle_id, 'snapshot_key': snapshot_key, 'task_key': task_key, 'phase': task.get('phase'), 'priority': task.get('priority'), 'task_title': task.get('title'), 'target': task.get('target'), 'owner': task.get('owner'), 'old_status': old_status, 'new_status': new_status, 'feedback_note': feedback_note or '', 'created_at': now})
    conn.commit()
    return task_key


def _row_to_dict(
    row: Any,
    columns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    兼容 sqlite3.Row 和普通 tuple。
    app.py 中的 conn 不一定设置 row_factory。
    """
    if row is None:
        return {}

    if hasattr(row, "keys"):
        return dict(row)

    if columns:
        return dict(zip(columns, row))

    return {}


def ensure_v12_feedback_logs_table(conn) -> None:
    conn.execute("\n        CREATE TABLE IF NOT EXISTS v12_feedback_logs (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            snapshot_key TEXT,\n            task_key TEXT,\n            phase TEXT,\n            priority TEXT,\n            task_title TEXT,\n            target TEXT,\n            owner TEXT,\n            old_status TEXT,\n            new_status TEXT,\n            feedback_note TEXT DEFAULT '',\n            created_at TEXT,\n            battle_id INTEGER,\n            FOREIGN KEY (battle_id)\n                REFERENCES battles(id)\n                ON UPDATE RESTRICT\n                ON DELETE RESTRICT\n        )\n    ")
    conn.execute('\n        CREATE INDEX IF NOT EXISTS\n        idx_p0s04_v12_feedback_logs_battle_lookup\n        ON v12_feedback_logs (\n            battle_id,\n            snapshot_key,\n            task_key,\n            id\n        )\n    ')
    conn.commit()


def load_execution_feedback_logs(conn, snapshot_key: str, limit: int=50, *, battle_id: int) -> List[Dict[str, Any]]:
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    ensure_v12_feedback_logs_table(conn)
    cursor = conn.execute('\n        SELECT *\n        FROM v12_feedback_logs\n        WHERE battle_id = ? AND snapshot_key = ?\n        ORDER BY id DESC\n        LIMIT ?\n    ', (battle_id, snapshot_key, limit))
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    return [_row_to_dict(row, columns) for row in rows]


def _first_value(row: Any) -> Any:
    if row is None:
        return None

    if hasattr(row, "keys"):
        keys = list(row.keys())
        if not keys:
            return None
        return row[keys[0]]

    try:
        return row[0]
    except Exception:
        return None


def load_feedback_logs_by_task_key(conn, task_key, limit=50, *, battle_id: int):
    """
    V13 Task Detail 使用：
    按 task_key 读取单个任务的反馈变更日志。

    注意：
    1. 这里只做数据读取。
    2. 不参与决策。
    3. 不修改反馈状态。
    4. 兼容 app.py 未设置 row_factory 的 sqlite 连接。
    """
    try:
        battle_id = int(battle_id)
    except (TypeError, ValueError):
        raise ValueError('battle_id is required')
    if battle_id <= 0:
        raise ValueError('battle_id is required')
    if not task_key:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute('\n            SELECT *\n            FROM v12_feedback_logs\n            WHERE battle_id = ? AND task_key = ?\n            ORDER BY id DESC\n            LIMIT ?\n            ', (battle_id, task_key, limit))
        rows = cursor.fetchall()
        columns = [item[0] for item in cursor.description]
        result = []
        for row in rows:
            item = {}
            for (index, column) in enumerate(columns):
                item[column] = row[index]
            result.append(item)
        return result
    except Exception:
        return []
