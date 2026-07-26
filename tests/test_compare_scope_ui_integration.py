from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _route_path(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    function = decorator.func
    if not (
        isinstance(function, ast.Attribute)
        and function.attr == "route"
        and decorator.args
    ):
        return None
    first = decorator.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def test_all_compare_render_paths_receive_scope_context() -> None:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))

    compare_nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            _route_path(decorator) == "/compare"
            for decorator in node.decorator_list
        )
    ]

    assert len(compare_nodes) == 1
    compare_node = compare_nodes[0]

    contexts: list[set[str]] = []

    for child in ast.walk(compare_node):
        if not isinstance(child, ast.Call):
            continue
        if not (
            isinstance(child.func, ast.Name)
            and child.func.id == "render_template"
            and child.args
            and isinstance(child.args[0], ast.Constant)
            and child.args[0].value == "compare.html"
        ):
            continue

        contexts.append(
            {
                keyword.arg
                for keyword in child.keywords
                if keyword.arg is not None
            }
        )

    required = {
        "analysis_scope_type",
        "analysis_scope_value",
        "analysis_scope",
        "scope_group_options",
        "scope_member_options",
    }

    assert len(contexts) == 3
    assert all(required <= context for context in contexts)


def test_compare_scope_template_contract() -> None:
    source = (ROOT / "templates/compare.html").read_text(encoding="utf-8")

    assert source.count('name="analysis_scope_type"') == 1
    assert source.count('name="analysis_scope_value"') == 1
    assert 'id="compare-scope-options"' in source

    for text in (
        "分析范围",
        "全同盟",
        "指定分组",
        "指定成员",
        "仅过滤下方成员明细",
        "不改变上方驾驶舱统计",
        "当前统计范围",
        "个人分析卡",
        "不代表同盟整体比例",
    ):
        assert text in source


def test_compare_scope_frontend_contract() -> None:
    javascript = (
        ROOT / "static/compare_attendance.js"
    ).read_text(encoding="utf-8")

    css = (
        ROOT / "static/compare_attendance.css"
    ).read_text(encoding="utf-8")

    for token in (
        "initialiseCompareScopeSelector",
        "analysis-scope-type",
        "analysis-scope-value",
        "compare-scope-options",
    ):
        assert token in javascript

    for token in (
        ".ca-analysis-scope-panel",
        ".ca-current-scope-caption",
        ".ca-member-scope-card",
    ):
        assert token in css
