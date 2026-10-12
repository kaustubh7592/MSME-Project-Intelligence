import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DEFAULT_DATABASE_URL = "postgresql+psycopg://msmeintel:msmeintel@localhost:5432/msmeintel"
VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


class ConfigurationError(ValueError):
    """Configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    log_level: str
    data_dir: Path


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Load and validate settings without filesystem or network side effects."""
    values = os.environ if environ is None else environ
    database_url = values.get("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
    log_level = values.get("MSMEINTEL_LOG_LEVEL", logging.getLevelName(logging.INFO)).upper()
    data_dir_value = values.get("MSMEINTEL_DATA_DIR", "./data").strip()

    if log_level not in VALID_LOG_LEVELS:
        raise ConfigurationError("MSMEINTEL_LOG_LEVEL must be a standard logging level.")
    if not data_dir_value:
        raise ConfigurationError("MSMEINTEL_DATA_DIR must not be empty.")

    try:
        parsed_url = make_url(database_url)
    except ArgumentError as error:
        raise ConfigurationError(
            "DATABASE_URL must be a valid SQLAlchemy PostgreSQL URL."
        ) from error
    if parsed_url.drivername != "postgresql+psycopg":
        raise ConfigurationError("DATABASE_URL must use the postgresql+psycopg driver.")

    return Settings(
        database_url=database_url,
        log_level=log_level,
        data_dir=Path(data_dir_value).expanduser(),
    )
