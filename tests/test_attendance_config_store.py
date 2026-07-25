from __future__ import annotations

import sqlite3
import unittest

from services.attendance_config_store import (
    TABLE_NAME,
    load_attendance_config,
    save_attendance_config,
    validate_attendance_config,
)


class AttendanceConfigStoreTests(
    unittest.TestCase
):
    def setUp(self):
        self.connection = sqlite3.connect(
            ":memory:"
        )

    def tearDown(self):
        self.connection.close()

    def test_default_config_is_battle_scoped(
        self,
    ):
        config = load_attendance_config(
            self.connection,
            5,
        )

        self.assertEqual(
            config["battle_id"],
            5,
        )

        self.assertFalse(
            config["persisted"]
        )

        self.assertEqual(
            config["thresholds"][
                "battle"
            ],
            5000.0,
        )

    def test_save_and_reload_custom_config(
        self,
    ):
        saved = save_attendance_config(
            self.connection,
            5,
            {
                "thresholds": {
                    "battle": 3000,
                    "assist": 300,
                    "donate": 80,
                },
                "weights": {
                    "battle": 60,
                    "assist": 40,
                    "donate": 0,
                },
                "enabled_metrics": {
                    "battle": True,
                    "assist": True,
                    "donate": False,
                },
                "auto_disable_empty_metrics":
                    True,
            },
        )

        loaded = load_attendance_config(
            self.connection,
            5,
        )

        self.assertTrue(
            saved["persisted"]
        )

        self.assertTrue(
            loaded["persisted"]
        )

        self.assertEqual(
            loaded["thresholds"][
                "battle"
            ],
            3000.0,
        )

        self.assertFalse(
            loaded["enabled_metrics"][
                "donate"
            ]
        )

        self.assertEqual(
            loaded["weights"]["assist"],
            40.0,
        )

    def test_battle_configs_are_isolated(
        self,
    ):
        save_attendance_config(
            self.connection,
            5,
            {
                "thresholds": {
                    "battle": 3000,
                },
            },
        )

        save_attendance_config(
            self.connection,
            6,
            {
                "thresholds": {
                    "battle": 1500,
                },
            },
        )

        battle_five = (
            load_attendance_config(
                self.connection,
                5,
            )
        )

        battle_six = (
            load_attendance_config(
                self.connection,
                6,
            )
        )

        self.assertEqual(
            battle_five["thresholds"][
                "battle"
            ],
            3000.0,
        )

        self.assertEqual(
            battle_six["thresholds"][
                "battle"
            ],
            1500.0,
        )

        row_count = self.connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            """
        ).fetchone()[0]

        self.assertEqual(
            row_count,
            2,
        )

    def test_enabled_weight_total_must_be_positive(
        self,
    ):
        with self.assertRaisesRegex(
            ValueError,
            "权重总和必须大于0",
        ):
            validate_attendance_config({
                "weights": {
                    "battle": 0,
                    "assist": 0,
                    "donate": 100,
                },
                "enabled_metrics": {
                    "battle": True,
                    "assist": True,
                    "donate": False,
                },
            })


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
