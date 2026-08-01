from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

import pytest


CANDIDATE_ROOT = Path(__file__).resolve().parents[1]

APP_PATH = CANDIDATE_ROOT / "app.py"

MODULE_PATH = (
    CANDIDATE_ROOT
    / "services"
    / "import_provenance.py"
)


def _source_and_tree(
    path: Path,
) -> tuple[str, ast.Module]:
    source = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    return (
        source,
        ast.parse(
            source,
            filename=str(path),
        ),
    )


def _dotted_name(
    node: ast.AST,
) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(
            node.value
        )

        return (
            f"{prefix}.{node.attr}"
            if prefix
            else node.attr
        )

    return ""


def _top_level_function(
    tree: ast.Module,
    name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    node = next(
        (
            item
            for item in tree.body
            if isinstance(
                item,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
            and item.name == name
        ),
        None,
    )

    assert node is not None, (
        f"missing function: {name}"
    )

    return node


def _has_main_guard(
    tree: ast.Module,
) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue

        expression = ast.unparse(
            node.test
        )

        if (
            "__name__"
            in expression
            and "__main__"
            in expression
        ):
            return True

    return False


def _find_restore_branch(
    source: str,
    save_node: (
        ast.FunctionDef
        | ast.AsyncFunctionDef
    ),
) -> ast.If:
    node = next(
        (
            item
            for item in ast.walk(
                save_node
            )
            if isinstance(item, ast.If)
            and "deleted_snapshot"
            in (
                ast.get_source_segment(
                    source,
                    item.test,
                )
                or ""
            )
        ),
        None,
    )

    assert node is not None, (
        "restore deleted snapshot branch is missing"
    )

    return node


def test_explicit_predeploy_migration_entry_exists(
) -> None:
    migration_path = (
        CANDIDATE_ROOT
        / "migrate_import_provenance.py"
    )

    assert migration_path.is_file(), (
        "explicit predeploy migration entry is missing"
    )

    source, tree = _source_and_tree(
        migration_path
    )

    calls_schema_migration = any(
        isinstance(node, ast.Call)
        and _dotted_name(
            node.func
        ).endswith(
            "ensure_snapshot_provenance_schema"
        )
        for node in ast.walk(tree)
    )

    assert calls_schema_migration, (
        "explicit migration entry does not call "
        "ensure_snapshot_provenance_schema"
    )

    assert _has_main_guard(tree), (
        "explicit migration entry is not executable"
    )

    assert "sqlite3" in source, (
        "explicit migration entry does not open "
        "a SQLite database"
    )


def test_runtime_validation_does_not_mutate_schema(
) -> None:
    source, tree = _source_and_tree(
        MODULE_PATH
    )

    validate_node = _top_level_function(
        tree,
        "validate_and_record_snapshot_counts",
    )

    calls_schema_ensure = any(
        isinstance(node, ast.Call)
        and _dotted_name(
            node.func
        ).endswith(
            "ensure_snapshot_provenance_schema"
        )
        for node in ast.walk(
            validate_node
        )
    )

    assert not calls_schema_ensure, (
        "validate_and_record_snapshot_counts "
        "still performs schema mutation"
    )

    validate_source = (
        ast.get_source_segment(
            source,
            validate_node,
        )
        or ""
    )

    assert "ALTER TABLE" not in validate_source.upper(), (
        "runtime validation contains ALTER TABLE"
    )


def test_restore_deleted_snapshot_validates_before_commit(
) -> None:
    source, tree = _source_and_tree(
        APP_PATH
    )

    save_node = _top_level_function(
        tree,
        "save_snapshot",
    )

    restore_node = _find_restore_branch(
        source,
        save_node,
    )

    validation_calls = [
        node
        for node in ast.walk(
            restore_node
        )
        if isinstance(node, ast.Call)
        and _dotted_name(
            node.func
        ).endswith(
            "validate_and_record_snapshot_counts"
        )
    ]

    assert validation_calls, (
        "restore branch does not call "
        "validate_and_record_snapshot_counts"
    )

    assert len(validation_calls) == 1, (
        "restore branch validation call count "
        f"is not one: {len(validation_calls)}"
    )

    validation_call = validation_calls[0]

    keyword_names = {
        keyword.arg
        for keyword in validation_call.keywords
        if keyword.arg is not None
    }

    assert {
        "battle_id",
        "snapshot_time",
        "source_member_count",
    } <= keyword_names, (
        "restore validation call lacks required "
        "cardinality arguments"
    )

    commit_lines = sorted(
        node.lineno
        for node in ast.walk(
            restore_node
        )
        if isinstance(node, ast.Call)
        and _dotted_name(
            node.func
        ).endswith(".commit")
    )

    assert commit_lines, (
        "restore branch commit is missing"
    )

    assert validation_call.lineno < min(
        commit_lines
    ), (
        "restore validation is not before commit"
    )

    return_true_lines = sorted(
        node.lineno
        for node in ast.walk(
            restore_node
        )
        if isinstance(node, ast.Return)
        and isinstance(
            node.value,
            ast.Constant,
        )
        and node.value.value is True
    )

    assert return_true_lines, (
        "restore branch successful return is missing"
    )

    assert validation_call.lineno < min(
        return_true_lines
    ), (
        "restore validation is not before return"
    )
