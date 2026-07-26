from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (
    ROOT / "templates/compare.html"
).read_text(encoding="utf-8")
JS = (
    ROOT / "static/compare_attendance.js"
).read_text(encoding="utf-8")
CSS = (
    ROOT / "static/compare_attendance.css"
).read_text(encoding="utf-8")


def test_excel_menu_has_two_modes():
    assert 'data-ca-export-mode="current_view"' in HTML
    assert 'data-ca-export-mode="smart_report"' in HTML
    assert "导出当前筛选结果" in HTML
    assert "导出智能分析报告" in HTML
    assert "data-ca-export-visible" not in HTML


def test_excel_request_uses_backend_route():
    assert 'fetch(' in JS
    assert '"/compare/export.xlsx"' in JS
    assert '"POST"' in JS
    assert '"Content-Type": "application/json"' in JS


def test_excel_request_sends_client_state():
    assert "context.activeFilter" in JS
    assert "context.sortState.column" in JS
    assert "context.sortState.direction" in JS
    assert "context.visibleColumns" in JS
    assert "status_filter" in JS
    assert "sort_column" in JS
    assert "sort_direction" in JS
    assert "visible_columns" in JS


def test_excel_menu_has_styles():
    assert ".ca-export-settings" in CSS
    assert ".ca-export-menu" in CSS
    assert ".ca-export-menu button" in CSS
