from __future__ import annotations

import sqlite3
from typing import Any


SOURCE_MEMBER_COUNT_COLUMN = (
    "source_member_count"
)

PERSISTED_MEMBER_COUNT_COLUMN = (
    "persisted_member_count"
)


class SnapshotCardinalityMismatch(
    RuntimeError
):
    """Imported and persisted member counts differ."""


def _normalize_member(
    value: Any,
) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() in {
        "",
        "nan",
        "none",
        "null",
        "nat",
    }:
        return ""

    return text


def count_source_members(
    frame: Any,
) -> int:
    columns = {
        str(column): column
        for column in getattr(
            frame,
            "columns",
            [],
        )
    }

    member_column = next(
        (
            columns[name]
            for name in (
                "成员",
                "member",
                "member_name",
            )
            if name in columns
        ),
        None,
    )

    if member_column is None:
        raise ValueError(
            "导入数据缺少成员列。"
        )

    values = frame[
        member_column
    ].tolist()

    members = {
        normalized
        for normalized in (
            _normalize_member(value)
            for value in values
        )
        if normalized
    }

    return len(members)


def ensure_snapshot_provenance_schema(
    connection: sqlite3.Connection,
) -> None:
    columns = {
        str(row[1]).lower()
        for row in connection.execute(
            "PRAGMA table_info(snapshots)"
        ).fetchall()
    }

    if not columns:
        raise RuntimeError(
            "snapshots表不存在。"
        )

    if (
        SOURCE_MEMBER_COUNT_COLUMN
        not in columns
    ):
        connection.execute(
            """
            ALTER TABLE snapshots
            ADD COLUMN source_member_count
            INTEGER
            """
        )

    if (
        PERSISTED_MEMBER_COUNT_COLUMN
        not in columns
    ):
        connection.execute(
            """
            ALTER TABLE snapshots
            ADD COLUMN persisted_member_count
            INTEGER
            """
        )


def count_persisted_members(
    connection: sqlite3.Connection,
    *,
    battle_id: int,
    snapshot_time: str,
) -> int:
    row = connection.execute(
        """
        SELECT COUNT(
            DISTINCT TRIM(member)
        )
        FROM player_records
        WHERE battle_id=?
          AND snapshot_time=?
          AND is_deleted=0
          AND TRIM(
              COALESCE(member, '')
          ) <> ''
        """,
        (
            battle_id,
            snapshot_time,
        ),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            "无法读取实际落库成员数。"
        )

    return int(row[0])


def validate_and_record_snapshot_counts(
    connection: sqlite3.Connection,
    *,
    battle_id: int,
    snapshot_time: str,
    source_member_count: int,
) -> int:
    if source_member_count < 0:
        raise ValueError(
            "源成员数不能为负数。"
        )


    persisted_member_count = (
        count_persisted_members(
            connection,
            battle_id=battle_id,
            snapshot_time=snapshot_time,
        )
    )

    if (
        persisted_member_count
        != source_member_count
    ):
        connection.rollback()

        raise SnapshotCardinalityMismatch(
            "导入成员数与实际落库成员数不一致："
            f"source={source_member_count}, "
            f"persisted={persisted_member_count}, "
            f"battle_id={battle_id}, "
            f"snapshot_time={snapshot_time}"
        )

    cursor = connection.execute(
        """
        UPDATE snapshots
        SET source_member_count=?,
            persisted_member_count=?
        WHERE battle_id=?
          AND snapshot_time=?
          AND is_deleted=0
        """,
        (
            source_member_count,
            persisted_member_count,
            battle_id,
            snapshot_time,
        ),
    )

    if cursor.rowcount != 1:
        connection.rollback()

        raise RuntimeError(
            "无法唯一更新快照溯源元数据："
            f"rowcount={cursor.rowcount}, "
            f"battle_id={battle_id}, "
            f"snapshot_time={snapshot_time}"
        )

    return persisted_member_count
