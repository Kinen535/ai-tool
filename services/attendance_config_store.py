from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from services.engines.attendance_engine import (
    ATTENDANCE_METRIC_CODES,
    normalize_enabled_metrics,
    normalize_thresholds,
)


TABLE_NAME = "attendance_battle_configs"

DEFAULT_THRESHOLDS = {
    "battle": 5000.0,
    "assist": 1000.0,
    "donate": 100.0,
}

DEFAULT_WEIGHTS = {
    "battle": 50.0,
    "assist": 30.0,
    "donate": 20.0,
}

DEFAULT_ENABLED_METRICS = {
    "battle": True,
    "assist": True,
    "donate": True,
}

DEFAULT_AUTO_DISABLE_EMPTY = True


def _utc_now_text() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _to_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return value != 0

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "enabled",
        "启用",
        "是",
    }


def default_attendance_config() -> dict[str, Any]:
    return {
        "thresholds": dict(
            DEFAULT_THRESHOLDS
        ),
        "weights": dict(
            DEFAULT_WEIGHTS
        ),
        "enabled_metrics": dict(
            DEFAULT_ENABLED_METRICS
        ),
        "auto_disable_empty_metrics":
            DEFAULT_AUTO_DISABLE_EMPTY,
        "config_version": 1,
    }


def validate_attendance_config(
    config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source = (
        dict(config)
        if isinstance(config, Mapping)
        else {}
    )

    threshold_input = dict(
        DEFAULT_THRESHOLDS
    )

    supplied_thresholds = source.get(
        "thresholds"
    )

    if isinstance(
        supplied_thresholds,
        Mapping,
    ):
        threshold_input.update(
            supplied_thresholds
        )

    thresholds = normalize_thresholds(
        threshold_input
    )

    enabled_input = dict(
        DEFAULT_ENABLED_METRICS
    )

    supplied_enabled = source.get(
        "enabled_metrics"
    )

    if isinstance(
        supplied_enabled,
        Mapping,
    ):
        enabled_input.update(
            supplied_enabled
        )

    enabled_metrics = (
        normalize_enabled_metrics(
            enabled_input
        )
    )

    weight_input = dict(
        DEFAULT_WEIGHTS
    )

    supplied_weights = source.get(
        "weights"
    )

    if isinstance(
        supplied_weights,
        Mapping,
    ):
        weight_input.update(
            supplied_weights
        )

    weights: dict[str, float] = {}

    for code in ATTENDANCE_METRIC_CODES:
        value = weight_input.get(
            code,
            0,
        )

        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                f"{code}权重必须是数字"
            ) from error

        if number < 0:
            raise ValueError(
                f"{code}权重不能小于0"
            )

        weights[code] = number

    enabled_weight_total = sum(
        weights[code]
        for code in ATTENDANCE_METRIC_CODES
        if enabled_metrics[code]
    )

    if enabled_weight_total <= 0:
        raise ValueError(
            "已启用指标的权重总和必须大于0"
        )

    auto_disable = _to_boolean(
        source.get(
            "auto_disable_empty_metrics",
            DEFAULT_AUTO_DISABLE_EMPTY,
        )
    )

    return {
        "thresholds": thresholds,
        "weights": weights,
        "enabled_metrics": enabled_metrics,
        "auto_disable_empty_metrics":
            auto_disable,
        "config_version": 1,
    }


def ensure_attendance_config_table(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            battle_id INTEGER PRIMARY KEY,
            thresholds_json TEXT NOT NULL,
            weights_json TEXT NOT NULL,
            enabled_metrics_json TEXT NOT NULL,
            auto_disable_empty INTEGER
                NOT NULL DEFAULT 1,
            config_version INTEGER
                NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        )
        """
    )


def load_attendance_config(
    connection: sqlite3.Connection,
    battle_id: int,
) -> dict[str, Any]:
    battle_id_value = int(battle_id)

    if battle_id_value <= 0:
        raise ValueError(
            "battle_id必须大于0"
        )

    ensure_attendance_config_table(
        connection
    )

    row = connection.execute(
        f"""
        SELECT
            thresholds_json,
            weights_json,
            enabled_metrics_json,
            auto_disable_empty,
            config_version,
            updated_at
        FROM {TABLE_NAME}
        WHERE battle_id=?
        """,
        (battle_id_value,),
    ).fetchone()

    if row is None:
        result = default_attendance_config()
        result["battle_id"] = battle_id_value
        result["persisted"] = False
        result["updated_at"] = ""
        return result

    config = validate_attendance_config({
        "thresholds": json.loads(row[0]),
        "weights": json.loads(row[1]),
        "enabled_metrics": json.loads(
            row[2]
        ),
        "auto_disable_empty_metrics":
            bool(row[3]),
    })

    config["battle_id"] = battle_id_value
    config["persisted"] = True
    config["config_version"] = int(
        row[4]
    )
    config["updated_at"] = str(
        row[5]
    )

    return config


def save_attendance_config(
    connection: sqlite3.Connection,
    battle_id: int,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    battle_id_value = int(battle_id)

    if battle_id_value <= 0:
        raise ValueError(
            "battle_id必须大于0"
        )

    normalized = (
        validate_attendance_config(
            config
        )
    )

    ensure_attendance_config_table(
        connection
    )

    updated_at = _utc_now_text()

    connection.execute(
        f"""
        INSERT INTO {TABLE_NAME} (
            battle_id,
            thresholds_json,
            weights_json,
            enabled_metrics_json,
            auto_disable_empty,
            config_version,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(battle_id)
        DO UPDATE SET
            thresholds_json=
                excluded.thresholds_json,
            weights_json=
                excluded.weights_json,
            enabled_metrics_json=
                excluded.enabled_metrics_json,
            auto_disable_empty=
                excluded.auto_disable_empty,
            config_version=
                excluded.config_version,
            updated_at=
                excluded.updated_at
        """,
        (
            battle_id_value,
            json.dumps(
                normalized["thresholds"],
                ensure_ascii=False,
                sort_keys=True,
            ),
            json.dumps(
                normalized["weights"],
                ensure_ascii=False,
                sort_keys=True,
            ),
            json.dumps(
                normalized[
                    "enabled_metrics"
                ],
                ensure_ascii=False,
                sort_keys=True,
            ),
            int(
                normalized[
                    "auto_disable_empty_metrics"
                ]
            ),
            int(
                normalized["config_version"]
            ),
            updated_at,
        ),
    )

    connection.commit()

    result = dict(normalized)
    result["battle_id"] = battle_id_value
    result["persisted"] = True
    result["updated_at"] = updated_at

    return result
