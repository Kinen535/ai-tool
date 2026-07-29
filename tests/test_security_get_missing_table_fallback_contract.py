from __future__ import annotations

import ast
import builtins
import datetime as datetime_module
import dis
import importlib.util
import ipaddress
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP_FILE = ROOT / "app.py"
AUDIT_FILE = (
    ROOT
    / "services"
    / "v155_security_admin_audit.py"
)


def _schema(
    connection: sqlite3.Connection,
) -> list[tuple[str, str]]:
    return [
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            """
            SELECT type, name
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()
    ]


def _load_audit_module():
    spec = importlib.util.spec_from_file_location(
        "test_v155_security_admin_audit",
        AUDIT_FILE,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


class _ExportCapability:
    def __bool__(self) -> bool:
        return False

    def __iter__(self):
        yield False
        yield "test-read-only"

    def __getitem__(self, index: int):
        return (False, "test-read-only")[index]


def _build_active_nginx_helper(
    temp_root: Path,
):
    source = APP_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    definitions = [
        node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name
        == "_v155_build_nginx_sync_report"
    ]

    assert definitions

    active = max(
        definitions,
        key=lambda node: node.lineno,
    )

    helper_source = ast.get_source_segment(
        source,
        active,
    )

    assert helper_source

    fake_snippet = (
        temp_root
        / "nginx"
        / "empty-security-deny.conf"
    )

    real_path = Path

    def safe_path(value: object = "."):
        candidate = real_path(value)

        if candidate.is_absolute():
            return fake_snippet

        return candidate

    namespace: dict[str, Any] = {
        "__builtins__": builtins.__dict__,
        "Any": Any,
        "Path": safe_path,
        "sqlite3": sqlite3,
        "ipaddress": ipaddress,
        "datetime": datetime_module.datetime,
        "can_export_to_nginx": (
            lambda *args, **kwargs: _ExportCapability()
        ),
    }

    exec(
        compile(
            helper_source,
            str(APP_FILE),
            "exec",
        ),
        namespace,
    )

    helper = namespace[
        "_v155_build_nginx_sync_report"
    ]

    for instruction in dis.get_instructions(helper):
        if instruction.opname != "LOAD_GLOBAL":
            continue

        name = str(instruction.argval)

        if (
            name not in helper.__globals__
            and not hasattr(builtins, name)
            and (
                "NGINX" in name.upper()
                or "SNIPPET" in name.upper()
            )
        ):
            helper.__globals__[name] = str(
                fake_snippet
            )

    return helper


def test_admin_audit_blank_db_returns_empty_without_schema_write() -> None:
    module = _load_audit_module()

    with tempfile.TemporaryDirectory(
        prefix="a15_4_38_a9_audit_"
    ) as value:
        db_path = Path(value) / "blank.sqlite3"
        connection = sqlite3.connect(db_path)

        before = _schema(connection)

        result = module.list_admin_actions(
            connection,
            page=1,
            per_page=8,
        )

        after = _schema(connection)
        connection.close()

    assert before == []
    assert after == []
    assert result["rows"] == []
    assert result["total"] == 0
    assert result["page"] == 1
    assert result["has_next"] is False
    assert result["has_prev"] is False


def test_nginx_report_blank_db_returns_empty_without_schema_write() -> None:
    with tempfile.TemporaryDirectory(
        prefix="a15_4_38_a9_nginx_"
    ) as value:
        temp_root = Path(value)
        data_dir = temp_root / "data"
        data_dir.mkdir(parents=True)

        db_path = data_dir / "snapshots.db"
        sqlite3.connect(db_path).close()

        helper = _build_active_nginx_helper(
            temp_root
        )

        original_cwd = Path.cwd()

        try:
            os.chdir(temp_root)

            before_connection = sqlite3.connect(
                db_path
            )

            before = _schema(before_connection)
            before_connection.close()

            result = helper()

            after_connection = sqlite3.connect(
                db_path
            )

            after = _schema(after_connection)
            after_connection.close()

        finally:
            os.chdir(original_cwd)

    assert before == []
    assert after == []
    assert result["active_block_count"] == 0
    assert result["active_blocks"] == []
    assert result["syncable_block_count"] == 0
    assert result["syncable_blocks"] == []
    assert result["missing_in_nginx"] == []
    assert result["extra_in_nginx"] == []
