from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
APP_PATH = REPO / "app.py"


def route_path(
    decorator: ast.expr,
) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None

    function = decorator.func

    if not (
        isinstance(function, ast.Attribute)
        and function.attr == "route"
    ):
        return None

    if not decorator.args:
        return None

    value = decorator.args[0]

    if (
        isinstance(value, ast.Constant)
        and isinstance(value.value, str)
    ):
        return value.value

    return None


class CompareScopeRouteIntegrationTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.app_source = APP_PATH.read_text(
            encoding="utf-8"
        )

        cls.tree = ast.parse(
            cls.app_source,
            filename=str(APP_PATH),
        )

        cls.compare_nodes = [
            node
            for node in cls.tree.body
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
            and any(
                route_path(decorator)
                == "/compare"
                for decorator
                in node.decorator_list
            )
        ]

        if len(cls.compare_nodes) != 1:
            raise AssertionError(
                "/compare路由数量异常："
                + str(len(cls.compare_nodes))
            )

        cls.compare_node = (
            cls.compare_nodes[0]
        )

        app_lines = (
            cls.app_source.splitlines(
                keepends=True
            )
        )

        cls.route_source = "".join(
            app_lines[
                cls.compare_node.lineno - 1:
                cls.compare_node.end_lineno
            ]
        )

    def test_compare_route_count(self):
        self.assertEqual(
            len(self.compare_nodes),
            1,
        )

    def test_scope_engine_is_imported(self):
        for token in (
            "from services.engines.compare_scope_engine import (",
            "normalize_compare_scope,",
            "select_compare_scope_rows,",
        ):
            self.assertIn(
                token,
                self.route_source,
            )

    def test_default_scope_is_alliance(self):
        self.assertIn(
            'analysis_scope_type = "alliance"',
            self.route_source,
        )

        self.assertIn(
            'analysis_scope_value = ""',
            self.route_source,
        )

        self.assertIn(
            "analysis_scope = normalize_compare_scope(",
            self.route_source,
        )

    def test_scope_form_contract_is_read(self):
        for field_name in (
            "analysis_scope_type",
            "analysis_scope_value",
        ):
            self.assertIn(
                f'"{field_name}"',
                self.route_source,
            )

        self.assertEqual(
            self.route_source.count(
                'request.form.get(\n'
                '            "analysis_scope_type"'
            ),
            1,
        )

        self.assertEqual(
            self.route_source.count(
                'request.form.get(\n'
                '            "analysis_scope_value"'
            ),
            1,
        )

    def test_scope_selection_precedes_compare_and_attendance(
        self,
    ):
        selection_position = (
            self.route_source.index(
                "scope_selection = "
                "select_compare_scope_rows("
            )
        )

        compare_position = (
            self.route_source.index(
                "result, groups, advice = "
                "compare_snapshots("
            )
        )

        attendance_position = (
            self.route_source.index(
                "build_compare_attendance_"
                "cache_payload("
            )
        )

        self.assertLess(
            selection_position,
            compare_position,
        )

        self.assertLess(
            selection_position,
            attendance_position,
        )

    def test_compare_and_attendance_use_scoped_frames(
        self,
    ):
        self.assertIn(
            "compare_snapshots(\n"
            "            scope_df_old,\n"
            "            scope_df_new",
            self.route_source,
        )

        self.assertIn(
            "build_compare_attendance_"
            "cache_payload(\n"
            "                scope_df_old,\n"
            "                scope_df_new",
            self.route_source,
        )

        self.assertEqual(
            self.route_source.count(
                "select_compare_scope_rows("
            ),
            1,
        )

    def test_scope_metadata_is_added_to_attendance(
        self,
    ):
        for token in (
            'attendance["分析范围"]',
            'attendance["范围"]["分析范围"]',
            'attendance["范围"]["范围人数"]',
            '"selected_member_count"',
        ):
            self.assertIn(
                token,
                self.route_source,
            )

    def test_scope_metadata_is_added_to_cache(
        self,
    ):
        for token in (
            '"analysis_scope_type"',
            '"analysis_scope_value"',
            '"analysis_scope"',
            '"analysis_scope_counts"',
        ):
            self.assertIn(
                token,
                self.route_source,
            )

    def test_cache_key_is_scope_isolated(self):
        for token in (
            "scope_cache_fragment",
            '"cache_fragment"',
            'f"__{scope_cache_fragment}"',
        ):
            self.assertIn(
                token,
                self.route_source,
            )

    def test_existing_detail_filters_remain(self):
        for field_name in (
            "team_keyword",
            "member_keyword",
            "power_growth_min",
            "power_growth_max",
            "war_min",
            "war_max",
            "assist_min",
            "assist_max",
            "donate_min",
            "donate_max",
        ):
            self.assertIn(
                field_name,
                self.route_source,
            )


if __name__ == "__main__":
    unittest.main()
