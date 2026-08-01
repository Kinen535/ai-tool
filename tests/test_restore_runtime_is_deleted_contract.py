from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def test_real_save_snapshot_restores_is_deleted_tombstone_and_rolls_back(
    tmp_path: Path,
) -> None:
    candidate_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    helper = (
        candidate_root
        / "tests"
        / "helpers"
        / "run_is_deleted_restore_runtime.py"
    )

    fixture_database = (
        candidate_root
        / "tests"
        / "fixtures"
        / "restore_runtime_fixture.db"
    )

    fixture_contract = (
        candidate_root
        / "tests"
        / "fixtures"
        / "restore_runtime_fixture.json"
    )

    for required_path in (
        candidate_root / "app.py",
        helper,
        fixture_database,
        fixture_contract,
    ):
        assert required_path.exists(), (
            f"永久恢复运行时输入不存在："
            f"{required_path}"
        )

    import_database = (
        tmp_path
        / "import.runtime.db"
    )

    success_database = (
        tmp_path
        / "success.runtime.db"
    )

    failure_database = (
        tmp_path
        / "failure.runtime.db"
    )

    for target in (
        import_database,
        success_database,
        failure_database,
    ):
        shutil.copy2(
            fixture_database,
            target,
        )

    project_database = (
        candidate_root
        / "data"
        / "snapshots.db"
    )

    project_database_before = (
        _sha256(project_database)
        if project_database.exists()
        else None
    )

    forbidden_database = (
        tmp_path
        / "forbidden-production.db"
    )

    result_path = (
        tmp_path
        / "runtime_result.json"
    )

    trace_path = (
        tmp_path
        / "runtime_trace.json"
    )

    environment = dict(
        os.environ
    )

    environment.update(
        {
            "HOME": str(
                tmp_path / "home"
            ),
            "XDG_CACHE_HOME": str(
                tmp_path / "xdg-cache"
            ),
            "XDG_CONFIG_HOME": str(
                tmp_path / "xdg-config"
            ),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(helper),
            str(candidate_root),
            str(import_database),
            str(success_database),
            str(failure_database),
            str(forbidden_database),
            str(fixture_contract),
            str(result_path),
            str(trace_path),
        ],
        cwd=str(candidate_root),
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    combined_output = (
        completed.stdout
        + "\n"
        + completed.stderr
    )

    assert completed.returncode == 0, (
        "真实is_deleted恢复运行时辅助程序失败：\n"
        + combined_output
    )

    assert result_path.exists(), (
        "运行时结果文件未生成。"
    )

    assert trace_path.exists(), (
        "运行时轨迹文件未生成。"
    )

    if project_database_before is not None:
        assert project_database.exists()

        assert _sha256(
            project_database
        ) == project_database_before, (
            "项目data/snapshots.db发生变化。"
        )

    result: dict[str, Any] = json.loads(
        result_path.read_text(
            encoding="utf-8",
        )
    )

    required_true = (
        "real_save_snapshot_called",
        "restore_branch_triggered",
        "successful_validation_observed",
        "successful_commit_observed",
        "successful_validation_before_commit",
        "metadata_id_reused",
        "metadata_restored_active",
        "player_records_restored_active",
        "no_duplicate_player_records",
        "forced_validation_failure_observed",
        "failure_rollback_observed",
        "failure_tombstone_state_unchanged",
        "failure_snapshot_remained_deleted",
        "failure_player_records_remained_deleted",
    )

    for field in required_true:
        assert result.get(field) is True, (
            f"恢复运行时合同未通过：{field}\n"
            + combined_output
        )

    assert (
        result[
            "production_database_used"
        ]
        is False
    )

    assert (
        result[
            "successful_rollback_observed"
        ]
        is False
    )

    assert (
        result[
            "failure_commit_observed"
        ]
        is False
    )

    assert (
        result[
            "restored_player_count"
        ]
        == result[
            "source_player_count"
        ]
    )

    assert (
        result[
            "restored_distinct_member_count"
        ]
        == result[
            "source_player_count"
        ]
    )

    assert (
        result[
            "source_member_count_recorded"
        ]
        == result[
            "source_player_count"
        ]
    )

    assert (
        result[
            "persisted_member_count_recorded"
        ]
        == result[
            "source_player_count"
        ]
    )

    assert result["classification"] == (
        "DIRECT_ISOLATED_IS_DELETED_"
        "RESTORE_SUCCESS_AND_VALIDATION_"
        "FAILURE_ROLLBACK_PASS"
    )

    assert result["result"] == "PASS"
