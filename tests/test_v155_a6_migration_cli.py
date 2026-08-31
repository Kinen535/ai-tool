from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

MIGRATION_PATH = (
    ROOT
    / "scripts"
    / "migrate_v155_a6_user_sessions.py"
)


def load_migration(label: str):
    spec = importlib.util.spec_from_file_location(
        f"v155_a6_migration_cli_{label}",
        MIGRATION_PATH,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(
        module
    )

    return module


def create_source_db(
    path: Path,
) -> None:
    conn = sqlite3.connect(
        str(path)
    )

    try:
        conn.execute(
            """
            CREATE TABLE v158_users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                session_version INTEGER
                    NOT NULL DEFAULT 1
            )
            """
        )

        conn.execute(
            """
            INSERT INTO v158_users (
                id,
                username,
                session_version
            )
            VALUES (1, 'test-user', 1)
            """
        )

        conn.commit()

    finally:
        conn.close()


def table_names(
    path: Path,
) -> set[str]:
    conn = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
    )

    try:
        return {
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                """
            )
        }

    finally:
        conn.close()


def run_main(
    module,
    monkeypatch,
    db: Path,
    *,
    allow_production: bool,
):
    argv = [
        str(MIGRATION_PATH),
        "--db",
        str(db),
    ]

    if allow_production:
        argv.append(
            "--allow-production"
        )

    monkeypatch.setattr(
        sys,
        "argv",
        argv,
    )

    return module.main()


def test_nonproduction_without_flag_succeeds(
    tmp_path,
    monkeypatch,
):
    db = tmp_path / "nonproduction.sqlite3"

    create_source_db(db)

    module = load_migration(
        "nonproduction"
    )

    assert (
        run_main(
            module,
            monkeypatch,
            db,
            allow_production=False,
        )
        == 0
    )

    tables = table_names(db)

    assert "v155_user_sessions" in tables
    assert "v155_user_session_policies" in tables


def test_production_without_flag_is_denied(
    tmp_path,
    monkeypatch,
):
    db = tmp_path / "production-denied.sqlite3"

    create_source_db(db)

    module = load_migration(
        "production_denied"
    )

    monkeypatch.setattr(
        module,
        "PRODUCTION_DB",
        db.resolve(),
    )

    with pytest.raises(
        SystemExit
    ) as exc_info:
        run_main(
            module,
            monkeypatch,
            db,
            allow_production=False,
        )

    assert exc_info.value.code == 2

    tables = table_names(db)

    assert "v155_user_sessions" not in tables
    assert "v155_user_session_policies" not in tables


def test_environment_cannot_bypass_production_guard(
    tmp_path,
    monkeypatch,
):
    db = tmp_path / "environment-denied.sqlite3"

    create_source_db(db)

    module = load_migration(
        "environment_denied"
    )

    monkeypatch.setattr(
        module,
        "PRODUCTION_DB",
        db.resolve(),
    )

    monkeypatch.setenv(
        "ALLOW_PRODUCTION",
        "1",
    )

    monkeypatch.setenv(
        "A6_ALLOW_PRODUCTION_MIGRATION",
        "1",
    )

    monkeypatch.setenv(
        "PRODUCTION_MIGRATION_AUTHORIZED",
        "YES",
    )

    with pytest.raises(
        SystemExit
    ) as exc_info:
        run_main(
            module,
            monkeypatch,
            db,
            allow_production=False,
        )

    assert exc_info.value.code == 2

    tables = table_names(db)

    assert "v155_user_sessions" not in tables
    assert "v155_user_session_policies" not in tables


def test_explicit_production_flag_authorizes(
    tmp_path,
    monkeypatch,
):
    db = tmp_path / "production-authorized.sqlite3"

    create_source_db(db)

    module = load_migration(
        "production_authorized"
    )

    monkeypatch.setattr(
        module,
        "PRODUCTION_DB",
        db.resolve(),
    )

    assert (
        run_main(
            module,
            monkeypatch,
            db,
            allow_production=True,
        )
        == 0
    )

    tables = table_names(db)

    assert "v155_user_sessions" in tables
    assert "v155_user_session_policies" in tables


def test_second_explicit_production_migration_is_idempotent(
    tmp_path,
    monkeypatch,
):
    db = tmp_path / "production-idempotent.sqlite3"

    create_source_db(db)

    module = load_migration(
        "production_idempotent"
    )

    monkeypatch.setattr(
        module,
        "PRODUCTION_DB",
        db.resolve(),
    )

    assert (
        run_main(
            module,
            monkeypatch,
            db,
            allow_production=True,
        )
        == 0
    )

    first_tables = table_names(db)

    assert (
        run_main(
            module,
            monkeypatch,
            db,
            allow_production=True,
        )
        == 0
    )

    second_tables = table_names(db)

    assert first_tables == second_tables
    assert "v155_user_sessions" in second_tables
    assert "v155_user_session_policies" in second_tables

    conn = sqlite3.connect(
        f"file:{db}?mode=ro",
        uri=True,
    )

    try:
        assert (
            conn.execute(
                "PRAGMA quick_check"
            ).fetchall()
            == [("ok",)]
        )

        assert (
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            == []
        )

    finally:
        conn.close()
