"""Configuration loading and reusable path resolution."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    data_dir: Path
    file1: Path
    file2: Path
    reports: Path
    key: tuple[str, ...]
    delimiter: str


def resolve_path(value: str, base: Path) -> Path:
    """Resolve absolute paths as-is and relative paths against base."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def load_config(env_file: str | Path = ".env") -> Config:
    """Load settings from dotenv and the process environment."""
    load_dotenv(env_file)

    data_dir_value = os.getenv("DATA_DIR")
    if not data_dir_value:
        raise ConfigError("DATA_DIR is required; set it in .env or the environment.")

    data_dir = Path(data_dir_value).expanduser().resolve()

    def configured_path(name: str) -> Path:
        value = os.getenv(name)
        if not value:
            raise ConfigError(f"{name} is required; set it in .env or the environment.")
        return resolve_path(value, data_dir)

    delimiter = os.getenv("DELIMITER", ",")
    delimiter = {"\\t": "\t", "tab": "\t"}.get(delimiter, delimiter)
    if len(delimiter) != 1 or delimiter in "\r\n":
        raise ConfigError(
            "DELIMITER must be one character. Use '\\t' for a tab delimiter."
        )

    key = tuple(part.strip() for part in os.getenv("KEY", "").split(",") if part.strip())

    return Config(
        data_dir=data_dir,
        file1=configured_path("FILE1"),
        file2=configured_path("FILE2"),
        reports=configured_path("REPORTS"),
        key=key,
        delimiter=delimiter,
    )
