import logging
from pathlib import Path

import pytest
from typer.testing import CliRunner

from msmeintel.cli import app
from msmeintel.config import ConfigurationError, load_settings
from msmeintel.database import Base, create_engine_from_settings
from msmeintel.logging_config import configure_logging

runner = CliRunner()
SECRET_URL = "postgresql+psycopg://private_user:supersecret@localhost/msmeintel"


def test_help_does_not_load_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "not a database URL")

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "health" in result.stdout


def test_health_redacts_credentials_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)

    result = runner.invoke(app, ["health"])

    assert result.exit_code == 0
    assert "Configuration OK" in result.stdout
    assert "connectivity was not checked" in result.stdout
    assert "private_user" not in result.stdout
    assert "supersecret" not in result.stdout
    assert "private_user" not in result.stderr
    assert "supersecret" not in result.stderr


def test_health_redacts_credentials_on_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)
    monkeypatch.setenv("MSMEINTEL_LOG_LEVEL", "LOUD")

    result = runner.invoke(app, ["health"])

    assert result.exit_code == 2
    assert "Configuration error" in result.stderr
    assert "private_user" not in result.stdout
    assert "supersecret" not in result.stdout
    assert "private_user" not in result.stderr
    assert "supersecret" not in result.stderr


def test_settings_honor_environment_overrides() -> None:
    settings = load_settings(
        {
            "DATABASE_URL": SECRET_URL,
            "MSMEINTEL_LOG_LEVEL": "debug",
            "MSMEINTEL_DATA_DIR": "alternate-data",
        }
    )

    assert settings.database_url == SECRET_URL
    assert settings.log_level == "DEBUG"
    assert settings.data_dir == Path("alternate-data")


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"MSMEINTEL_LOG_LEVEL": "LOUD"}, "MSMEINTEL_LOG_LEVEL"),
        ({"DATABASE_URL": "sqlite:///local.db"}, r"postgresql\+psycopg"),
    ],
)
def test_settings_reject_invalid_values(environment, message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        load_settings(environment)


def test_logging_configuration_is_idempotent() -> None:
    logger = configure_logging("INFO")
    first_handlers = tuple(logger.handlers)

    same_logger = configure_logging("DEBUG")

    assert same_logger is logger
    assert tuple(logger.handlers) == first_handlers
    assert logger.level == logging.DEBUG


def test_engine_is_lazy_and_uses_psycopg() -> None:
    settings = load_settings({"DATABASE_URL": SECRET_URL})

    engine = create_engine_from_settings(settings)
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.password == "supersecret"
    finally:
        engine.dispose()


def test_m00_metadata_is_empty() -> None:
    assert not Base.metadata.tables
