from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _literal_or_none(
    node: ast.AST,
) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def test_migration_requires_explicit_database_argument() -> None:
    candidate_root = (
        Path(__file__).resolve().parents[1]
    )

    migration_script = (
        candidate_root
        / "migrate_import_provenance.py"
    )

    assert migration_script.is_file(), (
        "migration entry is missing"
    )

    source = migration_script.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        source,
        filename=str(migration_script),
    )

    database_arguments: list[
        dict[str, object]
    ] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        function = node.func

        if not (
            isinstance(function, ast.Attribute)
            and function.attr == "add_argument"
        ):
            continue

        names = [
            argument.value
            for argument in node.args
            if isinstance(
                argument,
                ast.Constant,
            )
            and isinstance(
                argument.value,
                str,
            )
        ]

        if not names:
            continue

        normalized = " ".join(
            names
        ).lower()

        if not (
            "database" in normalized
            or "db" in normalized
        ):
            continue

        keywords = {
            keyword.arg: _literal_or_none(
                keyword.value
            )
            for keyword in node.keywords
            if keyword.arg is not None
        }

        database_arguments.append(
            {
                "names": names,
                "keywords": keywords,
            }
        )

    assert len(database_arguments) == 1, (
        "migration database argument definition "
        "must be unique"
    )

    database_argument = (
        database_arguments[0]
    )

    names = database_argument["names"]
    keywords = database_argument[
        "keywords"
    ]

    assert isinstance(names, list)
    assert isinstance(keywords, dict)

    optional_flag = any(
        str(name).startswith("-")
        for name in names
    )

    if optional_flag:
        explicitly_required = (
            keywords.get("required")
            is True
        )

    else:
        nargs = keywords.get("nargs")

        explicitly_required = (
            nargs not in {
                "?",
                "*",
            }
            and "default" not in keywords
        )

    assert explicitly_required, (
        "migration database argument must be "
        "explicitly required"
    )

    assert "default" not in keywords, (
        "migration database argument must not "
        "have an implicit default"
    )
