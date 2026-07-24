from __future__ import annotations

import copy
import unittest

from services.engines.attendance_engine import (
    OVERALL_ABSENT,
    OVERALL_ANOMALY,
    OVERALL_NO_BASELINE,
    OVERALL_QUALIFIED,
    STATUS_ABSENT,
    STATUS_ANOMALY,
    STATUS_BELOW,
    STATUS_EXEMPT,
    STATUS_NO_BASELINE,
    STATUS_QUALIFIED,
    build_attendance_dashboard,
    classify_growth,
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


class AttendanceEngineTests(unittest.TestCase):
    def test_classification_boundaries(self):
        self.assertEqual(
            classify_growth(0, 2000),
            STATUS_ABSENT,
        )
        self.assertEqual(
            classify_growth(1999, 2000),
            STATUS_BELOW,
        )
        self.assertEqual(
            classify_growth(2000, 2000),
            STATUS_QUALIFIED,
        )
        self.assertEqual(
            classify_growth(-1, 2000),
            STATUS_ANOMALY,
        )
        self.assertEqual(
            classify_growth(
                0,
                2000,
                exempt=True,
            ),
            STATUS_EXEMPT,
        )

    def test_dashboard_scope_and_statistics(self):
        start_rows = [
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
                "成员": "C",
                "分组": "一组",
                "战功总量": 0,
                "助攻总量": 0,
                "捐献总量": 0,
            },
            {
                "成员": "D",
                "分组": "二组",
                "战功总量": 0,
                "助攻总量": 0,
                "捐献总量": 0,
            },
            {
                "成员": "E",
                "分组": "二组",
                "战功总量": 20,
                "助攻总量": 0,
                "捐献总量": 0,
            },
            {
                "成员": "F",
                "分组": "二组",
                "战功总量": 0,
                "助攻总量": 0,
                "捐献总量": 0,
            },
            {
                "成员": "已离盟",
                "分组": "旧组",
                "战功总量": 99999,
                "助攻总量": 99999,
                "捐献总量": 99999,
            },
        ]

        end_rows = [
            {
                "成员": "A",
                "分组": "一组",
                "战功总量": 3000,
                "助攻总量": 500,
                "捐献总量": 100,
            },
            {
                "成员": "B",
                "分组": "一组",
                "战功总量": 1000,
                "助攻总量": 0,
                "捐献总量": 50,
            },
            {
                "成员": "C",
                "分组": "一组",
                "战功总量": 0,
                "助攻总量": 0,
                "捐献总量": 0,
            },
            {
                "成员": "D",
                "分组": "二组",
                "战功总量": 2500,
                "助攻总量": 350,
                "捐献总量": 150,
            },
            {
                "成员": "E",
                "分组": "二组",
                "战功总量": 10,
                "助攻总量": 100,
                "捐献总量": 0,
            },
            {
                "成员": "F",
                "分组": "二组",
                "战功总量": 0,
                "助攻总量": 0,
                "捐献总量": 0,
                "免考核": True,
            },
        ]

        original_start = copy.deepcopy(
            start_rows
        )
        original_end = copy.deepcopy(
            end_rows
        )

        result = build_attendance_dashboard(
            start_rows,
            end_rows,
            thresholds=THRESHOLDS,
            weights=WEIGHTS,
        )

        self.assertEqual(
            start_rows,
            original_start,
        )
        self.assertEqual(
            end_rows,
            original_end,
        )

        scope = result["范围"]

        self.assertEqual(
            scope["起始快照人数"],
            7,
        )
        self.assertEqual(
            scope["结束快照人数"],
            6,
        )
        self.assertEqual(
            scope["离开成员数"],
            1,
        )
        self.assertEqual(
            scope["离开成员名单"],
            ["已离盟"],
        )

        overview = result["同盟概览"]

        self.assertEqual(
            overview["总人数"],
            6,
        )
        self.assertEqual(
            overview["考核人数"],
            5,
        )
        self.assertEqual(
            overview["豁免人数"],
            1,
        )

        battle = overview["战功"]

        self.assertEqual(
            battle["有效考核人数"],
            4,
        )
        self.assertEqual(
            battle["合格人数"],
            2,
        )
        self.assertEqual(
            battle["未达标人数"],
            1,
        )
        self.assertEqual(
            battle["缺勤人数"],
            1,
        )
        self.assertEqual(
            battle["数据异常人数"],
            1,
        )
        self.assertEqual(
            battle["合格率"],
            50.0,
        )

        groups = {
            row["分组"]: row
            for row in result["分组概览"]
        }

        self.assertEqual(
            groups["二组"]["综合排名"],
            1,
        )
        self.assertEqual(
            groups["二组"]["综合考勤分"],
            75.0,
        )
        self.assertEqual(
            groups["一组"]["综合考勤分"],
            33.3,
        )

        members = {
            row["成员"]: row
            for row in result["成员明细"]
        }

        self.assertNotIn(
            "已离盟",
            members,
        )
        self.assertEqual(
            members["A"]["综合考勤状态"],
            OVERALL_QUALIFIED,
        )
        self.assertEqual(
            members["C"]["综合考勤状态"],
            OVERALL_ABSENT,
        )
        self.assertEqual(
            members["E"]["综合考勤状态"],
            OVERALL_ANOMALY,
        )
        self.assertEqual(
            members["F"]["战功考勤状态"],
            STATUS_EXEMPT,
        )

    def test_new_member_is_no_baseline(self):
        result = build_attendance_dashboard(
            [],
            [
                {
                    "成员": "新成员",
                    "分组": "新组",
                    "战功总量": 2500,
                    "助攻总量": 400,
                    "捐献总量": 120,
                }
            ],
            thresholds=THRESHOLDS,
        )

        member = result["成员明细"][0]
        overview = result["同盟概览"]

        self.assertEqual(
            result["范围"]["新增成员数"],
            1,
        )
        self.assertIsNone(
            member["战功增长"],
        )
        self.assertEqual(
            member["战功考勤状态"],
            STATUS_NO_BASELINE,
        )
        self.assertEqual(
            member["助攻考勤状态"],
            STATUS_NO_BASELINE,
        )
        self.assertEqual(
            member["捐献考勤状态"],
            STATUS_NO_BASELINE,
        )
        self.assertEqual(
            member["综合考勤状态"],
            OVERALL_NO_BASELINE,
        )
        self.assertEqual(
            member["是否有基线"],
            0,
        )
        self.assertEqual(
            overview["无基线人数"],
            1,
        )
        self.assertEqual(
            overview["有基线人数"],
            0,
        )
        self.assertEqual(
            overview["战功"]["无基线人数"],
            1,
        )
        self.assertEqual(
            overview["战功"]["有效考核人数"],
            0,
        )
        self.assertEqual(
            overview["战功"]["合格人数"],
            0,
        )

    def test_duplicate_member_is_rejected(self):
        with self.assertRaises(ValueError):
            build_attendance_dashboard(
                [],
                [
                    {
                        "成员": "重复",
                        "战功总量": 1,
                    },
                    {
                        "成员": "重复",
                        "战功总量": 2,
                    },
                ],
                thresholds=THRESHOLDS,
            )

    def test_invalid_config_is_rejected(self):
        with self.assertRaises(ValueError):
            build_attendance_dashboard(
                [],
                [],
                thresholds={
                    "battle": 1,
                    "assist": 1,
                },
            )

        with self.assertRaises(ValueError):
            build_attendance_dashboard(
                [],
                [],
                thresholds=THRESHOLDS,
                weights={
                    "battle": 0,
                    "assist": 0,
                    "donate": 0,
                },
            )

    def test_empty_dashboard(self):
        result = build_attendance_dashboard(
            [],
            [],
            thresholds=THRESHOLDS,
        )

        self.assertEqual(
            result["同盟概览"]["总人数"],
            0,
        )
        self.assertEqual(
            result["分组概览"],
            [],
        )
        self.assertEqual(
            result["成员明细"],
            [],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
