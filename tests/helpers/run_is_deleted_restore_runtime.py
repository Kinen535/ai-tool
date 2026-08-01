from __future__ import annotations

import importlib.util
import inspect
import json
import os
import shutil
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import pandas as pd


candidate_root = Path(
    sys.argv[1]
).resolve()

import_database = Path(
    sys.argv[2]
).resolve()

success_database = Path(
    sys.argv[3]
).resolve()

failure_database = Path(
    sys.argv[4]
).resolve()

production_database = Path(
    sys.argv[5]
).resolve()

fixture_path = Path(
    sys.argv[6]
).resolve()

result_path = Path(
    sys.argv[7]
).resolve()

trace_path = Path(
    sys.argv[8]
).resolve()

evidence_root = (
    success_database.parent.resolve()
)

app_path = (
    candidate_root
    / "app.py"
).resolve()

for required_path in (
    app_path,
    import_database,
    success_database,
    failure_database,
    fixture_path,
):
    if not required_path.exists():
        raise RuntimeError(
            "运行时输入不存在："
            f"{required_path}"
        )

for runtime_database in (
    import_database,
    success_database,
    failure_database,
):
    if runtime_database == (
        production_database
    ):
        raise RuntimeError(
            "隔离数据库与生产数据库路径相同。"
        )

fixture = json.loads(
    fixture_path.read_text(
        encoding="utf-8",
    )
)

if fixture[
    "fixture_mode"
] != (
    "CONVERT_EXISTING_METADATA_"
    "TO_DELETED_IN_ISOLATED_COPY"
):
    raise RuntimeError(
        "夹具模式不是转换既有元数据。"
    )

selected_group = fixture.get(
    "selected_group"
)

if not isinstance(
    selected_group,
    dict,
):
    raise RuntimeError(
        "选定隔离数据组不存在。"
    )

snapshot_time = selected_group.get(
    "snapshot_time"
)

battle_id = selected_group.get(
    "battle_id"
)

expected_group_count = int(
    selected_group.get(
        "row_count",
        0,
    )
)

if snapshot_time in (
    None,
    "",
):
    raise RuntimeError(
        "选定数据组缺少snapshot_time。"
    )

if battle_id is None:
    raise RuntimeError(
        "选定数据组缺少battle_id。"
    )

if expected_group_count <= 0:
    raise RuntimeError(
        "选定数据组人数无效。"
    )


def is_within(
    path: Path,
    root: Path,
) -> bool:
    return (
        path == root
        or root in path.parents
    )


def resolve_database_path(
    database: object,
) -> Path | None:
    try:
        text = os.fspath(database)
    except TypeError:
        return None

    if isinstance(text, bytes):
        text = os.fsdecode(text)

    if text == ":memory:":
        return None

    if text.startswith("file:"):
        parsed = urllib.parse.urlparse(
            text
        )

        raw_path = urllib.parse.unquote(
            parsed.path
        )

        if not raw_path:
            raw_path = text[
                len("file:"):
            ].split("?", 1)[0]

        path = Path(raw_path)

    else:
        path = Path(text)

    if not path.is_absolute():
        path = (
            Path.cwd()
            / path
        )

    return path.resolve()


real_connect = sqlite3.connect
current_database = import_database

active_events: list[str] | None = None

connection_requests: list[
    dict[str, Any]
] = []


class RecordingConnection(
    sqlite3.Connection
):
    def commit(self) -> None:
        if active_events is not None:
            active_events.append(
                "commit"
            )

        return super().commit()

    def rollback(self) -> None:
        if active_events is not None:
            active_events.append(
                "rollback"
            )

        return super().rollback()


def guarded_import_connect(
    database: object,
    *args: object,
    **kwargs: object,
) -> sqlite3.Connection:
    resolved = resolve_database_path(
        database
    )

    connection_requests.append(
        {
            "phase": "IMPORT",
            "requested": (
                os.fspath(database)
                if isinstance(
                    database,
                    (
                        str,
                        bytes,
                        os.PathLike,
                    ),
                )
                else repr(database)
            ),
            "resolved": (
                str(resolved)
                if resolved is not None
                else None
            ),
        }
    )

    if (
        resolved is not None
        and resolved
        == production_database
    ):
        raise RuntimeError(
            "连接守卫阻止打开生产数据库。"
        )

    if (
        resolved is not None
        and resolved.name
        == "snapshots.db"
    ):
        database = str(
            import_database
        )

        kwargs.pop(
            "uri",
            None,
        )

    elif (
        resolved is not None
        and is_within(
            resolved,
            candidate_root,
        )
    ):
        shadow_path = (
            evidence_root
            / (
                "candidate-shadow-"
                + resolved.name
            )
        )

        if (
            resolved.exists()
            and not shadow_path.exists()
        ):
            shutil.copy2(
                resolved,
                shadow_path,
            )

        database = str(
            shadow_path
        )

        kwargs.pop(
            "uri",
            None,
        )

    elif (
        resolved is not None
        and not is_within(
            resolved,
            evidence_root,
        )
    ):
        raise RuntimeError(
            "连接守卫阻止打开pytest临时目录外数据库："
            f"{resolved}"
        )

    return real_connect(
        database,
        *args,
        **kwargs,
    )


sqlite3.connect = guarded_import_connect

old_cwd = Path.cwd()

sys.path.insert(
    0,
    str(candidate_root),
)

os.chdir(candidate_root)

import services.v158_auth_config as _test_auth_config


# _A15_SYNTHETIC_CURRENT_BATTLE_CONTEXT_V1
def _a15_prepare_synthetic_current_battle(
    database_path: str,
    battle_id: int,
) -> None:
    import sqlite3 as _a15_sqlite3
    from pathlib import Path as _A15Path

    resolved_path = _A15Path(
        database_path
    ).resolve()

    production_path = _A15Path(
        "/home/admin/ai-tool/data/snapshots.db"
    ).resolve()

    if resolved_path == production_path:
        raise RuntimeError(
            "拒绝在永久恢复测试中打开生产数据库。"
        )

    if not resolved_path.is_file():
        raise RuntimeError(
            "隔离运行数据库不存在："
            f"{resolved_path}"
        )

    connection = _a15_sqlite3.connect(
        str(resolved_path)
    )

    try:
        connection.row_factory = _a15_sqlite3.Row

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError(
                "隔离运行数据库完整性异常："
                f"{resolved_path}: {integrity}"
            )

        columns = [
            {
                "name": str(row[1]),
                "type": str(row[2] or ""),
                "notnull": bool(row[3]),
                "default": row[4],
                "pk": int(row[5]),
            }
            for row in connection.execute(
                "PRAGMA table_info(battles)"
            ).fetchall()
        ]

        column_names = {
            column["name"]
            for column in columns
        }

        if not columns:
            raise RuntimeError(
                "隔离运行数据库缺少battles表。"
            )

        for required_column in (
            "id",
            "is_current",
        ):
            if required_column not in column_names:
                raise RuntimeError(
                    "battles表缺少必需字段："
                    f"{required_column}"
                )

        connection.execute(
            "UPDATE battles SET is_current=0"
        )

        existing = connection.execute(
            """
            SELECT id
            FROM battles
            WHERE id=?
            """,
            (battle_id,),
        ).fetchone()

        if existing is not None:
            connection.execute(
                """
                UPDATE battles
                SET is_current=1
                WHERE id=?
                """,
                (battle_id,),
            )

        else:
            insert_columns: list[str] = []
            insert_values: list[object] = []

            for column in columns:
                name = column["name"]
                lowered = name.lower()
                declared = column["type"].upper()

                if name == "id":
                    insert_columns.append(name)
                    insert_values.append(battle_id)
                    continue

                if name == "is_current":
                    insert_columns.append(name)
                    insert_values.append(1)
                    continue

                if not (
                    column["notnull"]
                    and column["default"] is None
                ):
                    continue

                insert_columns.append(name)

                if (
                    "name" in lowered
                    or "title" in lowered
                ):
                    insert_values.append(
                        f"SYNTHETIC_BATTLE_{battle_id}"
                    )

                elif "season_code" in lowered:
                    insert_values.append("TEST")

                elif "season_name" in lowered:
                    insert_values.append("SYNTHETIC")

                elif (
                    lowered.endswith("_at")
                    or "date" in lowered
                    or "time" in lowered
                ):
                    insert_values.append(
                        "2099-01-01 00:00:00"
                    )

                elif "INT" in declared:
                    insert_values.append(0)

                elif any(
                    token in declared
                    for token in (
                        "REAL",
                        "FLOA",
                        "DOUB",
                        "NUM",
                        "DEC",
                    )
                ):
                    insert_values.append(0.0)

                elif "BLOB" in declared:
                    insert_values.append(b"")

                else:
                    insert_values.append("synthetic")

            quoted_columns = ", ".join(
                '"'
                + name.replace('"', '""')
                + '"'
                for name in insert_columns
            )

            placeholders = ", ".join(
                "?"
                for _ in insert_columns
            )

            connection.execute(
                f"""
                INSERT INTO battles
                ({quoted_columns})
                VALUES ({placeholders})
                """,
                insert_values,
            )

        connection.commit()

        current_rows = connection.execute(
            """
            SELECT id
            FROM battles
            WHERE is_current=1
            ORDER BY id
            """
        ).fetchall()

        current_ids = [
            int(row[0])
            for row in current_rows
        ]

        if current_ids != [battle_id]:
            raise RuntimeError(
                "合成当前战场状态不唯一或ID错误："
                f"{current_ids}"
            )

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()



def _pytest_restore_runtime_secret_loader(
    *args: object,
    **kwargs: object,
) -> tuple[str, str]:
    return (
        "a" * 64,
        "pytest_restore_runtime",
    )


_test_auth_config.load_v158_session_secret = (
    _pytest_restore_runtime_secret_loader
)

module_name = (
    "a15_4_36_is_deleted_"
    "restore_runtime_candidate"
)

try:
    spec = (
        importlib.util
        .spec_from_file_location(
            module_name,
            app_path,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "无法创建候选app加载器。"
        )

    module = (
        importlib.util
        .module_from_spec(spec)
    )

    sys.modules[
        module_name
    ] = module

    spec.loader.exec_module(
        module
    )

finally:
    sqlite3.connect = real_connect
    os.chdir(old_cwd)


save_snapshot = getattr(
    module,
    "save_snapshot",
    None,
)

if not callable(save_snapshot):
    raise RuntimeError(
        "候选save_snapshot不可调用。"
    )

if list(
    inspect.signature(
        save_snapshot
    ).parameters
) != [
    "df",
    "snapshot_time",
    "source_filename",
]:
    raise RuntimeError(
        "save_snapshot运行时签名异常。"
    )

original_get_conn = getattr(
    module,
    "get_conn",
    None,
)

original_validation = getattr(
    module,
    "validate_and_record_snapshot_counts",
    None,
)

if not callable(original_get_conn):
    raise RuntimeError(
        "候选get_conn不可调用。"
    )

if not callable(
    original_validation
):
    raise RuntimeError(
        "候选人数核验函数不可调用。"
    )


def isolated_get_conn() -> sqlite3.Connection:
    connection_requests.append(
        {
            "phase": "SAVE_SNAPSHOT",
            "requested": str(
                current_database
            ),
            "resolved": str(
                current_database
            ),
        }
    )

    if current_database == (
        production_database
    ):
        raise RuntimeError(
            "隔离get_conn拒绝生产数据库。"
        )

    if not is_within(
        current_database,
        evidence_root,
    ):
        raise RuntimeError(
            "隔离get_conn拒绝证据目录外数据库。"
        )

    if active_events is None:
        connection = real_connect(
            str(current_database)
        )

    else:
        connection = real_connect(
            str(current_database),
            factory=RecordingConnection,
        )

    connection.row_factory = sqlite3.Row

    return connection


module.get_conn = isolated_get_conn

patched_battle_globals: dict[
    str,
    Any,
] = {}


def patch_battle_context(
    selected_battle_id: int,
) -> None:
    save_globals = (
        save_snapshot.__globals__
    )

    for name in (
        save_snapshot
        .__code__
        .co_names
    ):
        lowered = name.lower()

        if not (
            "battle" in lowered
            and "id" in lowered
        ):
            continue

        if name not in save_globals:
            continue

        value = save_globals[name]

        if callable(value):
            try:
                signature = (
                    inspect.signature(
                        value
                    )
                )
            except Exception:
                continue

            required = [
                parameter
                for parameter
                in signature.parameters.values()
                if (
                    parameter.default
                    is inspect.Parameter.empty
                    and parameter.kind
                    not in {
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    }
                )
            ]

            if required:
                continue

            patched_battle_globals[
                name
            ] = value

            save_globals[name] = (
                lambda value=selected_battle_id:
                value
            )

        elif isinstance(
            value,
            (
                int,
                str,
                type(None),
            ),
        ):
            patched_battle_globals[
                name
            ] = value

            save_globals[name] = (
                selected_battle_id
            )


patch_battle_context(
    int(battle_id)
)


def table_columns(
    connection: sqlite3.Connection,
    table: str,
) -> list[str]:
    safe_table = (
        '"'
        + table.replace(
            '"',
            '""',
        )
        + '"'
    )

    return [
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({safe_table})"
        ).fetchall()
    ]


def load_fixture(
    database: Path,
) -> tuple[
    pd.DataFrame,
    dict[str, Any],
]:
    connection = real_connect(
        str(database)
    )

    connection.row_factory = sqlite3.Row

    try:
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError(
                "隔离数据库完整性异常："
                f"{integrity}"
            )

        snapshot_columns = (
            table_columns(
                connection,
                "snapshots",
            )
        )

        player_columns = (
            table_columns(
                connection,
                "player_records",
            )
        )

        if "is_deleted" not in (
            snapshot_columns
        ):
            raise RuntimeError(
                "snapshots缺少is_deleted。"
            )

        if "deleted_at" in (
            snapshot_columns
        ):
            raise RuntimeError(
                "snapshots意外包含deleted_at。"
            )

        if "is_deleted" not in (
            player_columns
        ):
            raise RuntimeError(
                "player_records缺少is_deleted。"
            )

        metadata_rows = connection.execute(
            """
            SELECT *
            FROM snapshots
            WHERE snapshot_time = ?
              AND battle_id = ?
            ORDER BY id
            """,
            (
                snapshot_time,
                battle_id,
            ),
        ).fetchall()

        if len(metadata_rows) != 1:
            raise RuntimeError(
                "恢复查询键对应元数据数量不是1："
                f"{len(metadata_rows)}"
            )

        metadata = dict(
            metadata_rows[0]
        )

        player_rows = connection.execute(
            """
            SELECT
                member,
                group_name,
                battle_total,
                assist_total,
                donate_total,
                power_value
            FROM player_records
            WHERE snapshot_time = ?
              AND battle_id = ?
              AND COALESCE(is_deleted, 0) = 0
            ORDER BY rowid
            """,
            (
                snapshot_time,
                battle_id,
            ),
        ).fetchall()

        if len(player_rows) != (
            expected_group_count
        ):
            raise RuntimeError(
                "选定活动成员数量异常："
                f"{len(player_rows)}/"
                f"{expected_group_count}"
            )

        dataframe = pd.DataFrame(
            [
                dict(row)
                for row in player_rows
            ]
        ).rename(
            columns={
                "member": "成员",
                "group_name": "分组",
                "battle_total": "战功总量",
                "assist_total": "助攻总量",
                "donate_total": "捐献总量",
                "power_value": "势力值",
            }
        )

        expected_columns = [
            "成员",
            "分组",
            "战功总量",
            "助攻总量",
            "捐献总量",
            "势力值",
        ]

        if list(
            dataframe.columns
        ) != expected_columns:
            raise RuntimeError(
                "重建DataFrame字段异常："
                f"{list(dataframe.columns)}"
            )

        if dataframe.empty:
            raise RuntimeError(
                "重建DataFrame为空。"
            )

        if dataframe[
            "成员"
        ].isna().any():
            raise RuntimeError(
                "重建DataFrame存在空成员。"
            )

        return dataframe, metadata

    finally:
        connection.close()


def inspect_state(
    database: Path,
    metadata_id: int,
) -> dict[str, Any]:
    connection = real_connect(
        str(database)
    )

    connection.row_factory = sqlite3.Row

    try:
        metadata_row = connection.execute(
            """
            SELECT *
            FROM snapshots
            WHERE id = ?
            """,
            (
                metadata_id,
            ),
        ).fetchone()

        if metadata_row is None:
            raise RuntimeError(
                "运行后元数据记录丢失。"
            )

        active_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM player_records
                WHERE snapshot_time = ?
                  AND battle_id = ?
                  AND COALESCE(is_deleted, 0) = 0
                """,
                (
                    snapshot_time,
                    battle_id,
                ),
            ).fetchone()[0]
        )

        deleted_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM player_records
                WHERE snapshot_time = ?
                  AND battle_id = ?
                  AND COALESCE(is_deleted, 0) <> 0
                """,
                (
                    snapshot_time,
                    battle_id,
                ),
            ).fetchone()[0]
        )

        total_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM player_records
                WHERE snapshot_time = ?
                  AND battle_id = ?
                """,
                (
                    snapshot_time,
                    battle_id,
                ),
            ).fetchone()[0]
        )

        active_distinct_members = int(
            connection.execute(
                """
                SELECT COUNT(DISTINCT member)
                FROM player_records
                WHERE snapshot_time = ?
                  AND battle_id = ?
                  AND COALESCE(is_deleted, 0) = 0
                """,
                (
                    snapshot_time,
                    battle_id,
                ),
            ).fetchone()[0]
        )

        return {
            "metadata": dict(
                metadata_row
            ),
            "active_player_count": (
                active_count
            ),
            "deleted_player_count": (
                deleted_count
            ),
            "total_player_count": (
                total_count
            ),
            "active_distinct_member_count": (
                active_distinct_members
            ),
        }

    finally:
        connection.close()


def convert_to_tombstone(
    database: Path,
) -> tuple[
    pd.DataFrame,
    dict[str, Any],
    dict[str, Any],
]:
    dataframe, original_metadata = (
        load_fixture(database)
    )

    connection = real_connect(
        str(database)
    )

    connection.row_factory = sqlite3.Row

    try:
        connection.execute(
            """
            UPDATE snapshots
            SET is_deleted = 1
            WHERE id = ?
            """,
            (
                original_metadata["id"],
            ),
        )

        connection.execute(
            """
            UPDATE player_records
            SET is_deleted = 1
            WHERE snapshot_time = ?
              AND battle_id = ?
            """,
            (
                snapshot_time,
                battle_id,
            ),
        )

        connection.commit()

    finally:
        connection.close()

    deleted_state = inspect_state(
        database,
        int(original_metadata["id"]),
    )

    deleted_metadata = (
        deleted_state["metadata"]
    )

    if int(
        deleted_metadata["is_deleted"]
    ) != 1:
        raise RuntimeError(
            "快照元数据未转换为删除状态。"
        )

    if deleted_state[
        "active_player_count"
    ] != 0:
        raise RuntimeError(
            "转换删除状态后仍有活动成员记录。"
        )

    if deleted_state[
        "deleted_player_count"
    ] != len(dataframe):
        raise RuntimeError(
            "转换删除状态后的软删除人数异常。"
        )

    if deleted_state[
        "total_player_count"
    ] != len(dataframe):
        raise RuntimeError(
            "转换删除状态后成员总数发生变化。"
        )

    return (
        dataframe,
        original_metadata,
        deleted_state,
    )


success_dataframe, success_original, success_deleted = (
    convert_to_tombstone(
        success_database
    )
)

current_database = success_database

success_events: list[str] = []


def recording_validation(
    *args: Any,
    **kwargs: Any,
) -> Any:
    success_events.append(
        "validate"
    )

    return original_validation(
        *args,
        **kwargs,
    )


module.validate_and_record_snapshot_counts = (
    recording_validation
)

active_events = success_events

try:
    # _A15_SYNTHETIC_CURRENT_BATTLE_CONTEXT_V1
    for _a15_runtime_database in __import__('sys').argv[2:5]:
        _a15_prepare_synthetic_current_battle(
            _a15_runtime_database,
            5,
        )

    success_return = save_snapshot(
        success_dataframe.copy(
            deep=True
        ),
        snapshot_time,
        str(
            success_original[
                "source_filename"
            ]
        ),
    )

finally:
    active_events = None

    module.validate_and_record_snapshot_counts = (
        original_validation
    )


if "validate" not in success_events:
    raise RuntimeError(
        "成功恢复未观察到人数核验。"
    )

if "commit" not in success_events:
    raise RuntimeError(
        "成功恢复未观察到事务提交。"
    )

if "rollback" in success_events:
    raise RuntimeError(
        "成功恢复意外发生事务回滚。"
    )

if success_events.index(
    "validate"
) >= success_events.index(
    "commit"
):
    raise RuntimeError(
        "成功恢复人数核验未先于提交。"
    )

if "commit" in success_events[
    :success_events.index("validate")
]:
    raise RuntimeError(
        "成功恢复在核验前发生提交。"
    )

success_after = inspect_state(
    success_database,
    int(success_original["id"]),
)

success_metadata = (
    success_after["metadata"]
)

if int(
    success_metadata["is_deleted"]
) != 0:
    raise RuntimeError(
        "成功恢复后元数据仍为删除状态。"
    )

if success_after[
    "active_player_count"
] != len(success_dataframe):
    raise RuntimeError(
        "成功恢复后的活动成员数量异常。"
    )

if success_after[
    "deleted_player_count"
] != 0:
    raise RuntimeError(
        "成功恢复后仍有软删除成员记录。"
    )

if success_after[
    "total_player_count"
] != len(success_dataframe):
    raise RuntimeError(
        "成功恢复后成员总数异常或产生重复记录。"
    )

if success_after[
    "active_distinct_member_count"
] != len(success_dataframe):
    raise RuntimeError(
        "成功恢复后成员去重数量异常。"
    )

if int(
    success_metadata[
        "source_member_count"
    ]
) != len(success_dataframe):
    raise RuntimeError(
        "成功恢复source_member_count异常。"
    )

if int(
    success_metadata[
        "persisted_member_count"
    ]
) != len(success_dataframe):
    raise RuntimeError(
        "成功恢复persisted_member_count异常。"
    )

if int(
    success_metadata["id"]
) != int(
    success_original["id"]
):
    raise RuntimeError(
        "成功恢复未复用原元数据ID。"
    )


failure_dataframe, failure_original, failure_deleted = (
    convert_to_tombstone(
        failure_database
    )
)

current_database = failure_database

failure_events: list[str] = []


def failing_validation(
    *args: Any,
    **kwargs: Any,
) -> Any:
    failure_events.append(
        "validation_failure"
    )

    raise RuntimeError(
        "forced restore validation failure"
    )


module.validate_and_record_snapshot_counts = (
    failing_validation
)

active_events = failure_events

failure_exception: str | None = None

try:
    save_snapshot(
        failure_dataframe.copy(
            deep=True
        ),
        snapshot_time,
        str(
            failure_original[
                "source_filename"
            ]
        ),
    )

except Exception as error:
    failure_exception = (
        type(error).__name__
        + ": "
        + str(error)
    )

finally:
    active_events = None

    module.validate_and_record_snapshot_counts = (
        original_validation
    )


if failure_exception is None:
    raise RuntimeError(
        "强制人数核验失败未向外抛出异常。"
    )

if (
    "forced restore validation failure"
    not in failure_exception
):
    raise RuntimeError(
        "失败异常内容与强制核验异常不一致："
        f"{failure_exception}"
    )

if (
    "validation_failure"
    not in failure_events
):
    raise RuntimeError(
        "失败恢复未进入核验失败点。"
    )

if "rollback" not in failure_events:
    raise RuntimeError(
        "失败恢复未观察到事务回滚。"
    )

if "commit" in failure_events:
    raise RuntimeError(
        "失败恢复意外发生事务提交。"
    )

if failure_events.index(
    "validation_failure"
) >= failure_events.index(
    "rollback"
):
    raise RuntimeError(
        "失败恢复回滚未发生在核验失败之后。"
    )

failure_after = inspect_state(
    failure_database,
    int(failure_original["id"]),
)

if (
    failure_after
    != failure_deleted
):
    raise RuntimeError(
        "失败回滚后数据库状态未恢复到调用前软删除状态。"
    )


for request in connection_requests:
    resolved_text = request.get(
        "resolved"
    )

    if resolved_text is None:
        continue

    resolved = Path(
        resolved_text
    ).resolve()

    if resolved == production_database:
        raise RuntimeError(
            "运行记录显示曾请求生产数据库。"
        )


for name, value in (
    patched_battle_globals.items()
):
    save_snapshot.__globals__[
        name
    ] = value

module.get_conn = original_get_conn


result = {
    "candidate_app": str(app_path),
    "production_database": str(
        production_database
    ),
    "production_database_used": False,
    "fixture_mode": (
        "IS_DELETED_ONLY_TOMBSTONE"
    ),
    "snapshot_time": snapshot_time,
    "battle_id": battle_id,
    "source_filename": (
        success_original[
            "source_filename"
        ]
    ),
    "source_player_count": len(
        success_dataframe
    ),
    "real_save_snapshot_called": True,
    "restore_branch_triggered": True,
    "successful_restore_return": repr(
        success_return
    ),
    "successful_validation_observed": True,
    "successful_commit_observed": True,
    "successful_validation_before_commit": True,
    "successful_rollback_observed": False,
    "metadata_id_reused": True,
    "metadata_restored_active": True,
    "player_records_restored_active": True,
    "no_duplicate_player_records": True,
    "restored_player_count": (
        success_after[
            "active_player_count"
        ]
    ),
    "restored_distinct_member_count": (
        success_after[
            "active_distinct_member_count"
        ]
    ),
    "source_member_count_recorded": int(
        success_metadata[
            "source_member_count"
        ]
    ),
    "persisted_member_count_recorded": int(
        success_metadata[
            "persisted_member_count"
        ]
    ),
    "forced_validation_failure_observed": True,
    "failure_exception": (
        failure_exception
    ),
    "failure_rollback_observed": True,
    "failure_commit_observed": False,
    "failure_tombstone_state_unchanged": True,
    "failure_snapshot_remained_deleted": (
        int(
            failure_after[
                "metadata"
            ]["is_deleted"]
        )
        == 1
    ),
    "failure_player_records_remained_deleted": (
        failure_after[
            "active_player_count"
        ]
        == 0
        and failure_after[
            "deleted_player_count"
        ]
        == len(
            failure_dataframe
        )
    ),
    "success_events": success_events,
    "failure_events": failure_events,
    "patched_battle_globals": sorted(
        patched_battle_globals
    ),
    "connection_request_count": len(
        connection_requests
    ),
    "classification": (
        "DIRECT_ISOLATED_IS_DELETED_"
        "RESTORE_SUCCESS_AND_VALIDATION_"
        "FAILURE_ROLLBACK_PASS"
    ),
    "result": "PASS",
}

trace = {
    "success_events": (
        success_events
    ),
    "failure_events": (
        failure_events
    ),
    "connection_requests": (
        connection_requests
    ),
    "success_original_metadata": (
        success_original
    ),
    "success_deleted_state": (
        success_deleted
    ),
    "success_restored_state": (
        success_after
    ),
    "failure_original_metadata": (
        failure_original
    ),
    "failure_deleted_state": (
        failure_deleted
    ),
    "failure_after_state": (
        failure_after
    ),
    "patched_battle_globals": sorted(
        patched_battle_globals
    ),
}

result_path.write_text(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    + "\n",
    encoding="utf-8",
)

trace_path.write_text(
    json.dumps(
        trace,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    + "\n",
    encoding="utf-8",
)

print(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)
