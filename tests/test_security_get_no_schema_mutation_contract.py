from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_FILE = ROOT / "app.py"
AUDIT_FILE = (
    ROOT
    / "services"
    / "v155_security_admin_audit.py"
)

WRITE_SQL_PREFIXES = (
    "CREATE ",
    "ALTER ",
    "DROP ",
    "INSERT ",
    "UPDATE ",
    "DELETE ",
    "REPLACE ",
)


def _load(path: Path) -> tuple[str, ast.Module]:
    source = path.read_text(encoding="utf-8")
    return source, ast.parse(source)


def _definitions(
    tree: ast.Module,
    name: str,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name == name
    ]


def _call_name(call: ast.Call) -> str:
    node = call.func

    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parts = [node.attr]
        node = node.value

        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value

        if isinstance(node, ast.Name):
            parts.append(node.id)

        return ".".join(reversed(parts))

    return ""


def _executed_literal_sql(
    source: str,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    statements: list[str] = []

    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue

        if not _call_name(node).endswith(".execute"):
            continue

        if not node.args:
            continue

        argument = node.args[0]

        if not (
            isinstance(argument, ast.Constant)
            and isinstance(argument.value, str)
        ):
            continue

        statements.append(
            " ".join(argument.value.split())
        )

    return statements


def test_security_nginx_get_helper_executes_no_write_sql() -> None:
    source, tree = _load(APP_FILE)

    definitions = _definitions(
        tree,
        "_v155_build_nginx_sync_report",
    )

    assert definitions, (
        "未找到_v155_build_nginx_sync_report。"
    )

    active_definition = max(
        definitions,
        key=lambda node: node.lineno,
    )

    executed_sql = _executed_literal_sql(
        source,
        active_definition,
    )

    write_sql = [
        statement
        for statement in executed_sql
        if statement.upper().startswith(
            WRITE_SQL_PREFIXES
        )
    ]

    assert write_sql == [], (
        "GET /security/nginx的运行时帮助函数"
        f"仍执行写SQL：{write_sql}"
    )


def test_list_admin_actions_does_not_bootstrap_schema() -> None:
    _, tree = _load(AUDIT_FILE)

    definitions = _definitions(
        tree,
        "list_admin_actions",
    )

    assert len(definitions) == 1, (
        "list_admin_actions定义数量异常："
        f"{len(definitions)}"
    )

    calls = {
        _call_name(node).rsplit(".", 1)[-1]
        for node in ast.walk(definitions[0])
        if isinstance(node, ast.Call)
    }

    assert "ensure_admin_audit_table" not in calls, (
        "GET /security读取审计记录时"
        "仍调用ensure_admin_audit_table，"
        "会执行DDL及commit。"
    )
