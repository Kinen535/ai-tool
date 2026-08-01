from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from services.import_provenance import (
    SnapshotCardinalityMismatch,
    count_source_members,
    ensure_snapshot_provenance_schema,
    validate_and_record_snapshot_counts,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

APP_PATH = PROJECT_ROOT / "app.py"


class _Series:
    def __init__(
        self,
        values: list[object],
    ) -> None:
        self._values = values

    def tolist(
        self,
    ) -> list[object]:
        return list(
            self._values
        )


class _Frame:
    columns = ["成员"]

    def __init__(
        self,
        values: list[object],
    ) -> None:
        self._series = _Series(
            values
        )

    def __getitem__(
        self,
        key: str,
    ) -> _Series:
        if key != "成员":
            raise KeyError(key)

        return self._series


def _create_connection(
) -> sqlite3.Connection:
    connection = sqlite3.connect(
        ":memory:"
    )

    connection.execute(
        """
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY,
            snapshot_time TEXT NOT NULL,
            source_filename TEXT,
            battle_id INTEGER NOT NULL,
            is_deleted INTEGER NOT NULL
                DEFAULT 0
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE player_records (
            id INTEGER PRIMARY KEY,
            battle_id INTEGER NOT NULL,
            snapshot_time TEXT NOT NULL,
            member TEXT,
            is_deleted INTEGER NOT NULL
                DEFAULT 0
        )
        """
    )

    connection.commit()

    return connection


def _save_snapshot_contract(
) -> dict[str, object]:
    source = APP_PATH.read_text(
        encoding="utf-8",
        errors="replace",
    )

    tree = ast.parse(
        source,
        filename=str(APP_PATH),
    )

    save_node = next(
        (
            node
            for node in tree.body
            if (
                isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                )
                and node.name
                == "save_snapshot"
            )
        ),
        None,
    )

    if save_node is None:
        raise AssertionError(
            "未找到save_snapshot。"
        )

    player_insert_end = 0
    commit_lines: list[int] = []
    validation_lines: list[int] = []
    source_count_lines: list[int] = []

    for node in ast.walk(
        save_node
    ):
        if isinstance(
            node,
            ast.Assign,
        ):
            text = (
                ast.get_source_segment(
                    source,
                    node,
                )
                or ""
            )

            if (
                "source_member_count"
                in text
                and "count_source_members"
                in text
            ):
                source_count_lines.append(
                    node.lineno
                )

        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        call_name = ""

        if isinstance(
            node.func,
            ast.Name,
        ):
            call_name = (
                node.func.id
            )

        elif isinstance(
            node.func,
            ast.Attribute,
        ):
            call_name = (
                node.func.attr
            )

        if call_name == (
            "validate_and_record_snapshot_counts"
        ):
            validation_lines.append(
                node.lineno
            )

        if call_name == "commit":
            commit_lines.append(
                node.lineno
            )

        if call_name not in {
            "execute",
            "executemany",
        }:
            continue

        if not node.args:
            continue

        sql_node = node.args[0]

        if not (
            isinstance(
                sql_node,
                ast.Constant,
            )
            and isinstance(
                sql_node.value,
                str,
            )
        ):
            continue

        normalized = " ".join(
            sql_node.value.lower().split()
        )

        if (
            "insert into player_records"
            in normalized
        ):
            player_insert_end = max(
                player_insert_end,
                int(
                    node.end_lineno
                    or node.lineno
                ),
            )

    post_player_commits = sorted(
        line
        for line in commit_lines
        if line > player_insert_end
    )

    return {
        "source_count_lines": (
            sorted(
                source_count_lines
            )
        ),
        "player_insert_end": (
            player_insert_end
        ),
        "commit_lines": sorted(
            commit_lines
        ),
        "post_player_commits": (
            post_player_commits
        ),
        "validation_lines": sorted(
            validation_lines
        ),
    }


def test_snapshots_metadata_schema_records_source_and_persisted_counts(
) -> None:
    connection = (
        _create_connection()
    )

    try:
        ensure_snapshot_provenance_schema(
            connection
        )

        columns = {
            str(row[1]).lower()
            for row in connection.execute(
                "PRAGMA table_info(snapshots)"
            ).fetchall()
        }

        assert (
            "source_member_count"
            in columns
        )

        assert (
            "persisted_member_count"
            in columns
        )

    finally:
        connection.close()


def test_save_snapshot_persists_source_and_persisted_counts(
) -> None:
    frame = _Frame(
        [
            "成员A",
            "成员B",
            "成员A",
            "",
            None,
            "nan",
        ]
    )

    source_member_count = (
        count_source_members(
            frame
        )
    )

    assert source_member_count == 2

    connection = (
        _create_connection()
    )

    ensure_snapshot_provenance_schema(
        connection
    )

    connection.commit()

    try:
        connection.execute(
            "BEGIN"
        )

        connection.execute(
            """
            INSERT INTO snapshots (
                snapshot_time,
                source_filename,
                battle_id,
                is_deleted
            )
            VALUES (?, ?, ?, 0)
            """,
            (
                "2026-07-30 15:00:00",
                "test.csv",
                5,
            ),
        )

        connection.executemany(
            """
            INSERT INTO player_records (
                battle_id,
                snapshot_time,
                member,
                is_deleted
            )
            VALUES (?, ?, ?, 0)
            """,
            [
                (
                    5,
                    "2026-07-30 15:00:00",
                    "成员A",
                ),
                (
                    5,
                    "2026-07-30 15:00:00",
                    "成员B",
                ),
            ],
        )

        persisted = (
            validate_and_record_snapshot_counts(
                connection,
                battle_id=5,
                snapshot_time=(
                    "2026-07-30 15:00:00"
                ),
                source_member_count=(
                    source_member_count
                ),
            )
        )

        assert persisted == 2

        row = connection.execute(
            """
            SELECT
                source_member_count,
                persisted_member_count
            FROM snapshots
            WHERE battle_id=5
              AND snapshot_time=
                  '2026-07-30 15:00:00'
            """
        ).fetchone()

        assert row == (2, 2)

        contract = (
            _save_snapshot_contract()
        )

        assert len(
            contract[
                "source_count_lines"
            ]
        ) == 1

        commit_lines = sorted(
            contract["commit_lines"]
        )

        post_player_commits = sorted(
            contract["post_player_commits"]
        )

        validation_lines = sorted(
            contract["validation_lines"]
        )

        assert len(commit_lines) == 2

        assert len(post_player_commits) == 1

        assert len(validation_lines) == 2

        restore_validation_line = (
            validation_lines[0]
        )

        normal_validation_line = (
            validation_lines[1]
        )

        restore_commit_line = commit_lines[0]

        normal_commit_line = commit_lines[1]

        assert (
            restore_validation_line
            < restore_commit_line
        )

        assert (
            normal_validation_line
            < normal_commit_line
        )

        assert normal_commit_line == (
            post_player_commits[0]
        )

        validation_line = normal_validation_line

        commit_line = normal_commit_line

        final_commit_line = normal_commit_line




        player_insert_end = int(
            contract[
                "player_insert_end"
            ]
        )


        assert (
            player_insert_end
            < validation_line
            < final_commit_line
        )

    finally:
        connection.close()


def test_save_snapshot_verifies_player_records_count_before_commit(
) -> None:
    connection = (
        _create_connection()
    )

    try:
        connection.execute(
            "BEGIN"
        )

        connection.execute(
            """
            INSERT INTO snapshots (
                snapshot_time,
                source_filename,
                battle_id,
                is_deleted
            )
            VALUES (?, ?, ?, 0)
            """,
            (
                "2026-07-30 15:10:00",
                "mismatch.csv",
                5,
            ),
        )

        connection.execute(
            """
            INSERT INTO player_records (
                battle_id,
                snapshot_time,
                member,
                is_deleted
            )
            VALUES (?, ?, ?, 0)
            """,
            (
                5,
                "2026-07-30 15:10:00",
                "成员A",
            ),
        )

        with pytest.raises(
            SnapshotCardinalityMismatch
        ):
            validate_and_record_snapshot_counts(
                connection,
                battle_id=5,
                snapshot_time=(
                    "2026-07-30 15:10:00"
                ),
                source_member_count=2,
            )

        snapshot_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM snapshots
                WHERE snapshot_time=
                    '2026-07-30 15:10:00'
                """
            ).fetchone()[0]
        )

        player_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM player_records
                WHERE snapshot_time=
                    '2026-07-30 15:10:00'
                """
            ).fetchone()[0]
        )

        assert snapshot_count == 0
        assert player_count == 0

    finally:
        connection.close()
