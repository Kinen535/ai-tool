from __future__ import annotations

import os
import stat
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SESSION_SECRET_FILE = (
    PROJECT_ROOT
    / "data"
    / "v158_session_secret.txt"
)

SESSION_SECRET_ENV = "V158_SESSION_SECRET"

SESSION_COOKIE_SECURE_ENV = (
    "V158_SESSION_COOKIE_SECURE"
)

MIN_SESSION_SECRET_LENGTH = 64
MAX_SESSION_SECRET_LENGTH = 4096


def _validate_secret(
    value: Any,
    *,
    source: str,
) -> str:
    secret = str(value or "").strip()

    if len(secret) < MIN_SESSION_SECRET_LENGTH:
        raise RuntimeError(
            f"Session密钥长度不足：{source}"
        )

    if len(secret) > MAX_SESSION_SECRET_LENGTH:
        raise RuntimeError(
            f"Session密钥长度异常：{source}"
        )

    if any(
        ord(character) < 32
        for character in secret
    ):
        raise RuntimeError(
            f"Session密钥含控制字符：{source}"
        )

    return secret


def _parse_bool(
    value: Any,
    *,
    default: bool,
) -> bool:
    if value is None:
        return default

    normalized = str(value).strip().lower()

    if not normalized:
        return default

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise RuntimeError(
        "V158_SESSION_COOKIE_SECURE "
        "必须是true或false。"
    )


def load_v158_session_secret(
    *,
    env: Mapping[str, Any] | None = None,
    secret_file: str | Path | None = None,
) -> tuple[str, str]:
    environment = (
        os.environ
        if env is None
        else env
    )

    environment_secret = environment.get(
        SESSION_SECRET_ENV
    )

    if (
        environment_secret is not None
        and str(environment_secret).strip()
    ):
        secret = _validate_secret(
            environment_secret,
            source=(
                f"environment:"
                f"{SESSION_SECRET_ENV}"
            ),
        )

        return (
            secret,
            f"environment:{SESSION_SECRET_ENV}",
        )

    raw_path = Path(
        secret_file
        if secret_file is not None
        else DEFAULT_SESSION_SECRET_FILE
    ).expanduser()

    if not raw_path.is_absolute():
        raw_path = Path.cwd() / raw_path

    if raw_path.is_symlink():
        raise RuntimeError(
            "Session密钥文件不能是符号链接。"
        )

    path = raw_path.absolute()

    flags = os.O_RDONLY

    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        file_descriptor = os.open(
            path,
            flags,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Session密钥不存在：{path}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Session密钥文件无法安全打开：{path}"
        ) from exc

    try:
        file_stat = os.fstat(
            file_descriptor
        )

        if not stat.S_ISREG(
            file_stat.st_mode
        ):
            raise RuntimeError(
                "Session密钥路径不是普通文件。"
            )

        mode = stat.S_IMODE(
            file_stat.st_mode
        )

        if mode & 0o077:
            raise RuntimeError(
                "Session密钥文件权限必须为600。"
            )

        if (
            file_stat.st_size <= 0
            or file_stat.st_size
            > MAX_SESSION_SECRET_LENGTH + 2
        ):
            raise RuntimeError(
                "Session密钥文件大小异常。"
            )

        with os.fdopen(
            file_descriptor,
            "rb",
            closefd=False,
        ) as handle:
            raw_secret = handle.read(
                MAX_SESSION_SECRET_LENGTH + 3
            )

    finally:
        os.close(
            file_descriptor
        )

    try:
        decoded_secret = raw_secret.decode(
            "utf-8"
        )
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            "Session密钥文件不是有效UTF-8文本。"
        ) from exc

    secret = _validate_secret(
        decoded_secret,
        source=f"file:{path}",
    )

    return secret, f"file:{path}"


def build_v158_flask_session_config(
    *,
    env: Mapping[str, Any] | None = None,
    secret_file: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    environment = (
        os.environ
        if env is None
        else env
    )

    secret, source = (
        load_v158_session_secret(
            env=environment,
            secret_file=secret_file,
        )
    )

    cookie_secure = _parse_bool(
        environment.get(
            SESSION_COOKIE_SECURE_ENV
        ),
        default=False,
    )

    config = {
        "SECRET_KEY": secret,
        "SESSION_COOKIE_NAME": (
            "v158_auth_session"
        ),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": (
            cookie_secure
        ),
        "SESSION_COOKIE_PATH": "/",
        "PERMANENT_SESSION_LIFETIME": (
            timedelta(hours=12)
        ),
        "SESSION_REFRESH_EACH_REQUEST": (
            False
        ),
    }

    return config, source

# V15.5-A6 session registry enforcement.
# Default remains OFF until controlled A6-A6 cutover.
V155_SESSION_REGISTRY_ENFORCEMENT_ENV = (
    "V155_SESSION_REGISTRY_ENFORCEMENT"
)


def v155_session_registry_enforced() -> bool:
    raw = os.environ.get(
        V155_SESSION_REGISTRY_ENFORCEMENT_ENV,
        "",
    )

    return (
        str(raw)
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )
