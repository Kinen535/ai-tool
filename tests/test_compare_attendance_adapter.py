from __future__ import annotations

import copy
import math
import unittest

from services.engines.compare_attendance_adapter import (
    NOT_INCLUDED_STATUS,
    build_compare_attendance_context,
    enrich_compare_rows,
)


THRESHOLDS = {
    "battle": 2000,
    "assist": 300,
    "donate": 100,
}

WEIGHTS = {
    "battle": 50,
    "assist": 30,
    "donate": 20,
}


class FakeFrame:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)

    def to_dict(self, orient="records"):
        if orient != "records":
            raise ValueError(
                "只支持records"
            )

        return copy.deepcopy(self.rows)


class FakeScalar:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value


class CompareAttendanceAdapterTests(
    unittest.TestCase
):
    def setUp(self):
        self.start_rows = [
            {
                "成员": "A",
                "分组": "一组",
                "战功总量": 0,
                "助攻总量": 0,
                "捐献总量": 0,
            },
            {
                "成员": "B",
                "分组": "一组",
                "战功总量": 0,
                "助攻总量": 0,
                "捐献总量": 0,
            },
            {
                "成员": "已离开",
                "分组": "旧组",
                "战功总量": 5000,
                "助攻总量": 500,
                "捐献总量": 100,
            },
        ]

        self.end_rows = [
            {
                "成员": "A",
                "分组": "一组",
                "战功总量": 3000,
                "助攻总量": 500,
                "捐献总量": 120,
            },
            {
                "成员": "B",
                "分组": "一组",
                "战功总量": 0,
                "助攻总量": 0,
                "捐献总量": 0,
            },
            {
                "成员": "新成员",
                "分组": "二组",
                "战功总量": 9000,
                "助攻总量": 900,
                "捐献总量": 300,
            },
        ]

    def test_full_overview_not_reduced_by_visible_rows(
        self,
    ):
        context = build_compare_attendance_context(
            FakeFrame(self.start_rows),
            FakeFrame(self.end_rows),
            thresholds=THRESHOLDS,
            weights=WEIGHTS,
            visible_compare_rows=[
                {
                    "成员": "A",
                    "评分": 90,
                }
            ],
        )

        self.assertEqual(
            context["同盟概览"]["总人数"],
            3,
        )

        self.assertEqual(
            context["同盟概览"][
                "无基线人数"
            ],
            1,
        )

        self.assertEqual(
            len(context["当前显示明细"]),
            1,
        )

        self.assertTrue(
            context["适配契约"][
                "完整统计不受筛选影响"
            ]
        )

    def test_departed_compare_row_is_not_included(
        self,
    ):
        context = build_compare_attendance_context(
            self.start_rows,
            self.end_rows,
            thresholds=THRESHOLDS,
            visible_compare_rows=[
                {
                    "成员": "已离开",
                    "状态": "成员消失",
                }
            ],
        )

        row = context["当前显示明细"][0]

        self.assertEqual(
            row["考勤范围状态"],
            NOT_INCLUDED_STATUS,
        )

        self.assertEqual(
            row["综合考勤状态"],
            NOT_INCLUDED_STATUS,
        )

        self.assertEqual(
            row["考勤排除原因"],
            "不在结束快照",
        )

    def test_exempt_and_no_baseline_are_preserved(
        self,
    ):
        context = build_compare_attendance_context(
            self.start_rows,
            self.end_rows,
            thresholds=THRESHOLDS,
            exempt_names=["B"],
            visible_compare_rows=[
                {"成员": "B"},
                {"成员": "新成员"},
            ],
        )

        rows = {
            row["成员"]: row
            for row in context[
                "当前显示明细"
            ]
        }

        self.assertEqual(
            rows["B"]["是否免考核"],
            1,
        )

        self.assertEqual(
            rows["B"]["综合考勤状态"],
            "豁免",
        )

        self.assertEqual(
            rows["新成员"]["是否有基线"],
            0,
        )

        self.assertEqual(
            rows["新成员"]["综合考勤状态"],
            "无基线",
        )

    def test_growth_values_override_legacy_compare_values(
        self,
    ):
        context = build_compare_attendance_context(
            self.start_rows,
            self.end_rows,
            thresholds=THRESHOLDS,
            visible_compare_rows=[
                {
                    "成员": "新成员",
                    "战功增长": 9000,
                    "助攻增长": 900,
                    "捐献增长": 300,
                }
            ],
        )

        row = context["当前显示明细"][0]

        self.assertIsNone(
            row["战功增长"]
        )
        self.assertIsNone(
            row["助攻增长"]
        )
        self.assertIsNone(
            row["捐献增长"]
        )

    def test_output_is_json_safe(self):
        end_rows = copy.deepcopy(
            self.end_rows
        )

        end_rows[0]["非数字空值"] = math.nan
        end_rows[0]["模拟标量"] = FakeScalar(7)

        context = build_compare_attendance_context(
            self.start_rows,
            end_rows,
            thresholds=THRESHOLDS,
        )

        member = {
            row["成员"]: row
            for row in context[
                "完整成员明细"
            ]
        }["A"]

        self.assertIsNone(
            member["非数字空值"]
        )

        self.assertEqual(
            member["模拟标量"],
            7,
        )

    def test_inputs_are_not_mutated(self):
        start_before = copy.deepcopy(
            self.start_rows
        )
        end_before = copy.deepcopy(
            self.end_rows
        )

        build_compare_attendance_context(
            self.start_rows,
            self.end_rows,
            thresholds=THRESHOLDS,
        )

        self.assertEqual(
            self.start_rows,
            start_before,
        )

        self.assertEqual(
            self.end_rows,
            end_before,
        )

    def test_missing_member_is_rejected(self):
        with self.assertRaises(ValueError):
            build_compare_attendance_context(
                [],
                [
                    {
                        "分组": "一组",
                        "战功总量": 1,
                    }
                ],
                thresholds=THRESHOLDS,
            )

    def test_enrich_compare_rows_requires_member(self):
        dashboard = (
            build_compare_attendance_context(
                self.start_rows,
                self.end_rows,
                thresholds=THRESHOLDS,
            )["考勤驾驶舱"]
        )

        with self.assertRaises(ValueError):
            enrich_compare_rows(
                [{"评分": 90}],
                dashboard,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
