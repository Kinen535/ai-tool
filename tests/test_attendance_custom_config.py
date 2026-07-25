from __future__ import annotations

import inspect
import unittest
from copy import deepcopy
from unittest.mock import patch

import services.engines.attendance_engine as engine
import services.engines.compare_attendance_adapter as adapter


def fake_dashboard(
    *args,
    thresholds,
    weights=None,
    **kwargs,
):
    normalized_weights = engine.normalize_weights(
        weights
    )

    metric_template = {
        "合格率": 50.0,
        "合格人数": 1,
        "参与人数": 1,
        "缺勤人数": 0,
        "未达标人数": 0,
        "数据异常": 0,
        "总增长": 100,
    }

    overview = {
        "战功": deepcopy(metric_template),
        "助攻": {
            **deepcopy(metric_template),
            "参与人数": 0,
            "总增长": 0,
        },
        "捐献": {
            **deepcopy(metric_template),
            "参与人数": 0,
            "总增长": 0,
        },
        "综合考勤分": 50.0,
    }

    return {
        "同盟概览": overview,
        "分组概览": [
            {
                "分组": "测试组",
                **deepcopy(overview),
            }
        ],
        "成员明细": [
            {
                "成员": "测试成员",
                "战功考勤状态": "合格",
                "助攻考勤状态": "缺勤",
                "捐献考勤状态": "缺勤",
            }
        ],
        "配置": {
            "考核标准": dict(
                thresholds
            ),
            "权重": normalized_weights,
        },
        "范围": {},
        "默认排序": [],
    }


class AttendanceCustomConfigTests(
    unittest.TestCase
):
    def test_all_metrics_disabled_is_rejected(
        self,
    ):
        with self.assertRaisesRegex(
            ValueError,
            "至少启用一项考勤指标",
        ):
            engine.normalize_enabled_metrics({
                "battle": False,
                "assist": False,
                "donate": False,
            })

    def test_disabled_metrics_receive_zero_weight(
        self,
    ):
        with patch.object(
            engine,
            "build_attendance_dashboard",
            side_effect=fake_dashboard,
        ):
            dashboard = (
                engine
                .build_configurable_attendance_dashboard(
                    start_rows=[],
                    end_rows=[],
                    thresholds={
                        "battle": 3000,
                        "assist": 300,
                        "donate": 100,
                    },
                    weights={
                        "battle": 50,
                        "assist": 30,
                        "donate": 20,
                    },
                    enabled_metrics={
                        "battle": True,
                        "assist": False,
                        "donate": False,
                    },
                )
            )

        config = dashboard["配置"]

        self.assertEqual(
            config["权重"],
            {
                "battle": 1.0,
                "assist": 0.0,
                "donate": 0.0,
            },
        )

        member = dashboard["成员明细"][0]

        self.assertEqual(
            member["助攻考勤状态"],
            "未纳入",
        )

        self.assertEqual(
            member["捐献考勤状态"],
            "未纳入",
        )

        self.assertFalse(
            dashboard["同盟概览"][
                "助攻"
            ]["是否启用"]
        )

    def test_empty_metrics_can_be_auto_disabled(
        self,
    ):
        with patch.object(
            engine,
            "build_attendance_dashboard",
            side_effect=fake_dashboard,
        ) as mocked:
            dashboard = (
                engine
                .build_configurable_attendance_dashboard(
                    start_rows=[],
                    end_rows=[],
                    thresholds={
                        "battle": 3000,
                        "assist": 300,
                        "donate": 100,
                    },
                    weights={
                        "battle": 50,
                        "assist": 30,
                        "donate": 20,
                    },
                    enabled_metrics={
                        "battle": True,
                        "assist": True,
                        "donate": True,
                    },
                    auto_disable_empty_metrics=True,
                )
            )

        self.assertEqual(
            mocked.call_count,
            2,
        )

        self.assertEqual(
            dashboard["配置"][
                "自动停用指标"
            ],
            [
                "assist",
                "donate",
            ],
        )

        self.assertEqual(
            dashboard["配置"]["权重"],
            {
                "battle": 1.0,
                "assist": 0.0,
                "donate": 0.0,
            },
        )

    def test_default_wrapper_is_backward_compatible(
        self,
    ):
        sentinel = {
            "原始结果": True,
        }

        with patch.object(
            engine,
            "build_attendance_dashboard",
            return_value=sentinel,
        ) as mocked:
            result = (
                engine
                .build_configurable_attendance_dashboard(
                    start_rows=[],
                    end_rows=[],
                    thresholds={
                        "battle": 5000,
                        "assist": 1000,
                        "donate": 100,
                    },
                )
            )

        self.assertIs(
            result,
            sentinel,
        )

        self.assertEqual(
            mocked.call_count,
            1,
        )

    def test_adapter_accepts_configuration_parameters(
        self,
    ):
        context_signature = inspect.signature(
            adapter
            .build_compare_attendance_context
        )

        cache_signature = inspect.signature(
            adapter
            .build_compare_attendance_cache_payload
        )

        for signature in (
            context_signature,
            cache_signature,
        ):
            self.assertIn(
                "enabled_metrics",
                signature.parameters,
            )

            self.assertIn(
                "auto_disable_empty_metrics",
                signature.parameters,
            )

        context_source = inspect.getsource(
            adapter
            .build_compare_attendance_context
        )

        cache_source = inspect.getsource(
            adapter
            .build_compare_attendance_cache_payload
        )

        self.assertIn(
            "enabled_metrics=enabled_metrics",
            context_source,
        )

        self.assertIn(
            "auto_disable_empty_metrics="
            "auto_disable_empty_metrics",
            context_source,
        )

        self.assertIn(
            "enabled_metrics=enabled_metrics",
            cache_source,
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
