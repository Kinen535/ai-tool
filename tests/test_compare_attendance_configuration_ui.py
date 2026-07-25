from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from jinja2 import Environment


REPO = Path(__file__).resolve().parents[1]

APP_PATH = REPO / "app.py"
TEMPLATE_PATH = REPO / "templates" / "compare.html"
CSS_PATH = REPO / "static" / "compare_attendance.css"
JS_PATH = REPO / "static" / "compare_attendance.js"


class CompareAttendanceConfigurationUiTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.app_source = APP_PATH.read_text(
            encoding="utf-8"
        )

        cls.template_source = (
            TEMPLATE_PATH.read_text(
                encoding="utf-8"
            )
        )

        cls.css_source = CSS_PATH.read_text(
            encoding="utf-8"
        )

        cls.javascript_source = (
            JS_PATH.read_text(
                encoding="utf-8"
            )
        )

        ast.parse(cls.app_source)

        Environment().parse(
            cls.template_source
        )

    def test_route_uses_battle_configuration_store(
        self,
    ):
        for token in (
            "default_attendance_config",
            "load_attendance_config",
            "save_attendance_config",
            "ATTENDANCE_CONFIG_TABLE",
            "_load_attendance_form_config",
            "_attendance_form_payload",
        ):
            self.assertIn(
                token,
                self.app_source,
            )

        self.assertIn(
            "SELECT 1\n"
            "                FROM sqlite_master",
            self.app_source,
        )

    def test_route_reads_all_configuration_fields(
        self,
    ):
        expected_fields = {
            "attendance_threshold_battle",
            "attendance_threshold_assist",
            "attendance_threshold_donate",
            "attendance_weight_battle",
            "attendance_weight_assist",
            "attendance_weight_donate",
            "attendance_enable_battle",
            "attendance_enable_assist",
            "attendance_enable_donate",
            "attendance_auto_disable_empty",
        }

        for field_name in expected_fields:
            self.assertIn(
                field_name,
                self.app_source,
            )

            self.assertIn(
                f'name="{field_name}"',
                self.template_source,
            )

    def test_route_forwards_enabled_and_auto_disable(
        self,
    ):
        self.assertIn(
            "enabled_metrics=(",
            self.app_source,
        )

        self.assertIn(
            "attendance_enabled_metrics",
            self.app_source,
        )

        self.assertIn(
            "auto_disable_empty_metrics=(",
            self.app_source,
        )

        self.assertIn(
            "attendance_auto_disable_empty",
            self.app_source,
        )

    def test_template_receives_configuration_on_all_paths(
        self,
    ):
        self.assertGreaterEqual(
            self.app_source.count(
                "attendance_config="
                "attendance_config"
            ),
            2,
        )

        self.assertIn(
            'cached_data[\n'
            '                    "attendance_config"\n'
            '                ] = attendance_config',
            self.app_source,
        )

    def test_template_configuration_editor_contract(
        self,
    ):
        for token in (
            "data-attendance-config-form",
            "考勤标准设置",
            "纳入战功考核",
            "纳入助攻考核",
            "纳入捐献考核",
            "自动将该项标记为“未纳入”",
            "权重会自动归一化",
        ):
            self.assertIn(
                token,
                self.template_source,
            )

    def test_styles_and_javascript_contract(
        self,
    ):
        self.assertIn(
            ".ca-attendance-config-editor",
            self.css_source,
        )

        self.assertIn(
            ".ca-attendance-config-grid",
            self.css_source,
        )

        self.assertIn(
            "initialiseAttendanceConfigurationForm",
            self.javascript_source,
        )

        self.assertIn(
            "至少启用一项考勤指标",
            self.javascript_source,
        )

        self.assertIn(
            "权重总和必须大于0",
            self.javascript_source,
        )

    def test_no_duplicate_form_field_names(
        self,
    ):
        names = re.findall(
            r'\bname=["\']([^"\']+)["\']',
            self.template_source,
        )

        expected_once = (
            "attendance_threshold_battle",
            "attendance_threshold_assist",
            "attendance_threshold_donate",
            "attendance_weight_battle",
            "attendance_weight_assist",
            "attendance_weight_donate",
            "attendance_enable_battle",
            "attendance_enable_assist",
            "attendance_enable_donate",
            "attendance_auto_disable_empty",
        )

        for field_name in expected_once:
            self.assertEqual(
                names.count(field_name),
                1,
                field_name,
            )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
