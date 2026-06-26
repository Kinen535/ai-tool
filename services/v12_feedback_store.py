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
    conn.execute("""
    CREATE TABLE IF NOT EXISTS v12_execution_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        snapshot_key TEXT,
        task_key TEXT,

        phase TEXT,
        priority TEXT,
        task_title TEXT,
        target TEXT,
        owner TEXT,

        status TEXT DEFAULT 'pending',
        feedback_note TEXT DEFAULT '',

        created_at TEXT,
        updated_at TEXT,

        UNIQUE(snapshot_key, task_key)
    )
    """)
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


def load_execution_feedback_records(
    conn,
    snapshot_key: str,
) -> List[Dict[str, Any]]:
    ensure_v12_execution_feedback_table(conn)

    cursor = conn.execute("""
        SELECT *
        FROM v12_execution_feedback
        WHERE snapshot_key = ?
        ORDER BY id ASC
    """, (snapshot_key,))

    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    return [
        _row_to_dict(row, columns)
        for row in rows
    ]


def get_feedback_map(
    feedback_records: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    return {
        item.get("task_key"): item
        for item in feedback_records
        if item.get("task_key")
    }


def save_execution_feedback(
    conn,
    snapshot_key: str,
    task: Dict[str, Any],
    status: str,
    feedback_note: str = "",
) -> str:
    """
    保存单条任务反馈。

    V12 Phase F：
    每次状态变化都会写入 v12_feedback_logs，形成审计轨迹。
    """
    ensure_v12_execution_feedback_table(conn)
    ensure_v12_feedback_logs_table(conn)

    task_key = build_task_key(task)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_status = status or "pending"

    old_row = conn.execute("""
        SELECT status
        FROM v12_execution_feedback
        WHERE snapshot_key = ?
          AND task_key = ?
        LIMIT 1
    """, (snapshot_key, task_key)).fetchone()

    old_status = _first_value(old_row) or "pending"

    params = {
        "snapshot_key": snapshot_key,
        "task_key": task_key,

        "phase": task.get("phase"),
        "priority": task.get("priority"),
        "task_title": task.get("title"),
        "target": task.get("target"),
        "owner": task.get("owner"),

        "status": new_status,
        "feedback_note": feedback_note or "",

        "created_at": now,
        "updated_at": now,
    }

    conn.execute("""
        INSERT INTO v12_execution_feedback (
            snapshot_key,
            task_key,
            phase,
            priority,
            task_title,
            target,
            owner,
            status,
            feedback_note,
            created_at,
            updated_at
        )
        VALUES (
            :snapshot_key,
            :task_key,
            :phase,
            :priority,
            :task_title,
            :target,
            :owner,
            :status,
            :feedback_note,
            :created_at,
            :updated_at
        )
        ON CONFLICT(snapshot_key, task_key)
        DO UPDATE SET
            status = excluded.status,
            feedback_note = excluded.feedback_note,
            updated_at = excluded.updated_at
    """, params)

    # 只有状态变化或备注不为空时才写日志，避免重复点击制造噪音。
    if old_status != new_status or feedback_note:
        conn.execute("""
            INSERT INTO v12_feedback_logs (
                snapshot_key,
                task_key,
                phase,
                priority,
                task_title,
                target,
                owner,
                old_status,
                new_status,
                feedback_note,
                created_at
            )
            VALUES (
                :snapshot_key,
                :task_key,
                :phase,
                :priority,
                :task_title,
                :target,
                :owner,
                :old_status,
                :new_status,
                :feedback_note,
                :created_at
            )
        """, {
            "snapshot_key": snapshot_key,
            "task_key": task_key,
            "phase": task.get("phase"),
            "priority": task.get("priority"),
            "task_title": task.get("title"),
            "target": task.get("target"),
            "owner": task.get("owner"),
            "old_status": old_status,
            "new_status": new_status,
            "feedback_note": feedback_note or "",
            "created_at": now,
        })

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
    conn.execute("""
    CREATE TABLE IF NOT EXISTS v12_feedback_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        snapshot_key TEXT,
        task_key TEXT,

        phase TEXT,
        priority TEXT,
        task_title TEXT,
        target TEXT,
        owner TEXT,

        old_status TEXT,
        new_status TEXT,
        feedback_note TEXT DEFAULT '',

        created_at TEXT
    )
    """)
    conn.commit()


def load_execution_feedback_logs(
    conn,
    snapshot_key: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    ensure_v12_feedback_logs_table(conn)

    cursor = conn.execute("""
        SELECT *
        FROM v12_feedback_logs
        WHERE snapshot_key = ?
        ORDER BY id DESC
        LIMIT ?
    """, (snapshot_key, limit))

    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    return [
        _row_to_dict(row, columns)
        for row in rows
    ]


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
