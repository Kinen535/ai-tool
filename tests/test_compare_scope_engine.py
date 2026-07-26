from __future__ import annotations

import copy
import unittest

from services.engines.compare_scope_engine import (
    SCOPE_ALLIANCE,
    SCOPE_GROUP,
    SCOPE_MEMBER,
    build_compare_scope_cache_identity,
    normalize_compare_scope,
    select_compare_scope_rows,
)


class CompareScopeEngineTests(
    unittest.TestCase
):
    def setUp(self):
        self.start_rows = [
            {
                "成员": "甲",
                "分组": "旧组",
                "战功总量": 100,
            },
            {
                "成员": "乙",
                "分组": "一组",
                "战功总量": 200,
            },
            {
                "成员": "离开成员",
                "分组": "一组",
                "战功总量": 300,
            },
        ]

        self.end_rows = [
            {
                "成员": "甲",
                "分组": "一组",
                "战功总量": 500,
            },
            {
                "成员": "乙",
                "分组": "二组",
                "战功总量": 600,
            },
            {
                "成员": "新成员",
                "分组": "一组",
                "战功总量": 50,
            },
        ]

    def test_default_scope_is_alliance(self):
        scope = normalize_compare_scope()

        self.assertEqual(
            scope["scope_type"],
            SCOPE_ALLIANCE,
        )

        self.assertEqual(
            scope["scope_value"],
            "",
        )

        self.assertEqual(
            scope["scope_label"],
            "全同盟",
        )

    def test_alliance_scope_ignores_value(self):
        scope = normalize_compare_scope(
            SCOPE_ALLIANCE,
            "不应保留",
        )

        self.assertEqual(
            scope["scope_value"],
            "",
        )

    def test_group_scope_requires_value(self):
        with self.assertRaises(
            ValueError
        ):
            normalize_compare_scope(
                SCOPE_GROUP,
                " ",
            )

    def test_member_scope_requires_value(self):
        with self.assertRaises(
            ValueError
        ):
            normalize_compare_scope(
                SCOPE_MEMBER,
                None,
            )

    def test_invalid_scope_is_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            normalize_compare_scope(
                "unknown",
                "值",
            )

    def test_alliance_preserves_full_snapshots(self):
        result = select_compare_scope_rows(
            self.start_rows,
            self.end_rows,
        )

        self.assertEqual(
            len(result["start_rows"]),
            3,
        )

        self.assertEqual(
            len(result["end_rows"]),
            3,
        )

        self.assertEqual(
            result["counts"][
                "departed_member_count"
            ],
            1,
        )

        self.assertEqual(
            result["counts"][
                "new_member_count"
            ],
            1,
        )

    def test_group_uses_end_snapshot_membership(
        self,
    ):
        result = select_compare_scope_rows(
            self.start_rows,
            self.end_rows,
            SCOPE_GROUP,
            "一组",
        )

        self.assertEqual(
            result["selected_member_names"],
            ["甲", "新成员"],
        )

        self.assertEqual(
            [
                row["成员"]
                for row in result["start_rows"]
            ],
            ["甲"],
        )

        self.assertEqual(
            result["counts"][
                "baseline_member_count"
            ],
            1,
        )

        self.assertEqual(
            result["counts"][
                "new_member_count"
            ],
            1,
        )

    def test_group_scope_does_not_include_members_who_moved_out(
        self,
    ):
        result = select_compare_scope_rows(
            self.start_rows,
            self.end_rows,
            SCOPE_GROUP,
            "一组",
        )

        self.assertNotIn(
            "乙",
            result["selected_member_names"],
        )

    def test_unknown_group_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "没有找到分组",
        ):
            select_compare_scope_rows(
                self.start_rows,
                self.end_rows,
                SCOPE_GROUP,
                "不存在组",
            )

    def test_member_scope_carries_baseline(self):
        result = select_compare_scope_rows(
            self.start_rows,
            self.end_rows,
            SCOPE_MEMBER,
            "甲",
        )

        self.assertEqual(
            result["selected_member_names"],
            ["甲"],
        )

        self.assertEqual(
            result["start_rows"][0]["分组"],
            "旧组",
        )

        self.assertEqual(
            result["end_rows"][0]["分组"],
            "一组",
        )

        self.assertEqual(
            result["counts"][
                "baseline_member_count"
            ],
            1,
        )

    def test_new_member_scope_has_no_baseline(
        self,
    ):
        result = select_compare_scope_rows(
            self.start_rows,
            self.end_rows,
            SCOPE_MEMBER,
            "新成员",
        )

        self.assertEqual(
            result["start_rows"],
            [],
        )

        self.assertEqual(
            result["counts"][
                "new_member_count"
            ],
            1,
        )

    def test_unknown_member_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "没有找到成员",
        ):
            select_compare_scope_rows(
                self.start_rows,
                self.end_rows,
                SCOPE_MEMBER,
                "不存在成员",
            )

    def test_duplicate_members_are_rejected(self):
        duplicate_end = (
            self.end_rows
            + [
                {
                    "成员": "甲",
                    "分组": "一组",
                }
            ]
        )

        with self.assertRaisesRegex(
            ValueError,
            "重复成员",
        ):
            select_compare_scope_rows(
                self.start_rows,
                duplicate_end,
            )

    def test_inputs_are_not_mutated(self):
        start_before = copy.deepcopy(
            self.start_rows
        )

        end_before = copy.deepcopy(
            self.end_rows
        )

        select_compare_scope_rows(
            self.start_rows,
            self.end_rows,
            SCOPE_GROUP,
            "一组",
        )

        self.assertEqual(
            self.start_rows,
            start_before,
        )

        self.assertEqual(
            self.end_rows,
            end_before,
        )

    def test_scope_cache_identity_is_stable(self):
        first = (
            build_compare_scope_cache_identity(
                SCOPE_GROUP,
                " 一组 ",
            )
        )

        second = (
            build_compare_scope_cache_identity(
                SCOPE_GROUP,
                "一组",
            )
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertTrue(
            first["cache_fragment"].startswith(
                "scope:group:"
            )
        )

    def test_scope_cache_identity_separates_types(
        self,
    ):
        group_identity = (
            build_compare_scope_cache_identity(
                SCOPE_GROUP,
                "甲",
            )
        )

        member_identity = (
            build_compare_scope_cache_identity(
                SCOPE_MEMBER,
                "甲",
            )
        )

        self.assertNotEqual(
            group_identity["scope_digest"],
            member_identity["scope_digest"],
        )

    def test_scope_contract_separates_detail_filters(
        self,
    ):
        result = select_compare_scope_rows(
            self.start_rows,
            self.end_rows,
            SCOPE_GROUP,
            "一组",
        )

        self.assertTrue(
            result["contract"][
                "scope_applied_before_dashboard"
            ]
        )

        self.assertTrue(
            result["contract"][
                "detail_filters_are_separate"
            ]
        )

        self.assertTrue(
            result["contract"][
                "group_and_member_use_end_snapshot"
            ]
        )

        self.assertFalse(
            result["contract"][
                "input_rows_mutated"
            ]
        )


if __name__ == "__main__":
    unittest.main()
