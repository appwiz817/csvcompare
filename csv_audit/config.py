"""Configuration loading and reusable path resolution."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised for missing or invalid configuration."""


@dataclass(frozen=True)
class Config:
    data_dir: Path
    file1: Path
    file2: Path
    reports: Path
    key: tuple[str, ...]
    delimiter: str


def resolve_path(value: str, base: Path) -> Path:
    """Resolve an absolute path as-is, or a relative path against base."""
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def load_config(env_file: str | Path = ".env") -> Config:
    """Load required paths and optional comparison settings from dotenv."""
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
        raise ConfigError("DELIMITER must be exactly one character (use \\t for tab).")

    key = tuple(part.strip() for part in os.getenv("KEY", "").split(",") if part.strip())
    return Config(data_dir, configured_path("FILE1"), configured_path("FILE2"),
                  configured_path("REPORTS"), key, delimiter)
