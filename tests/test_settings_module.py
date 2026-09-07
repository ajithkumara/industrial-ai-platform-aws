"""
Automated, CI-safe unit tests for config/settings.py (AWS-native).

Proves the same lazy-validation invariant the Azure reference guarantees:
importing config.settings must NOT crash or require any production
environment variables to be present. Validation of required settings is
opt-in and explicit via validate_settings(), called only from real entry
points (the Kinesis consumer main(), the Kinesis producer __init__) — never
automatically at import time.

Only the environment-variable names change from the Azure reference
(EVENTHUB_* / STORAGE_* -> KINESIS_* / S3_* / AWS_REGION); the contract is
identical and is NOT weakened.
"""

import importlib

import pytest


_RELEVANT_VARS = (
    "KINESIS_STREAM_NAME",
    "KINESIS_CONSUMER_NAME",
    "AWS_REGION",
    "S3_BUCKET",
    "RAW_FOLDER",
    "RAW_BATCH_SIZE",
    "CONSUMER_BATCH_SIZE",
    "CHECKPOINT_TABLE",
)


def _reload_settings_without_dotenv_or_env(monkeypatch):
    """
    Reload config.settings with no relevant environment variables set AND
    with dotenv disabled, so a developer-local .env file (present on disk but
    git-ignored) cannot leak real values into this test and mask the behavior
    under test.
    """
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)

    for var in _RELEVANT_VARS:
        monkeypatch.delenv(var, raising=False)

    import config.settings as settings_module

    importlib.reload(settings_module)
    return settings_module


def test_importing_settings_module_does_not_require_env_vars(monkeypatch):
    """
    Importing config.settings with no relevant environment variables set
    (and no .env file loaded) must succeed (not raise), even though the
    resulting settings object will contain empty/default values.
    """
    settings_module = _reload_settings_without_dotenv_or_env(monkeypatch)

    assert settings_module.settings.kinesis.stream_name == ""
    assert settings_module.settings.storage.bucket == ""


def test_validate_settings_raises_only_when_called_explicitly(monkeypatch):
    """
    validate_settings() must still correctly detect missing required
    configuration when called explicitly (it is not a no-op) — it simply must
    not run automatically on import.
    """
    settings_module = _reload_settings_without_dotenv_or_env(monkeypatch)

    with pytest.raises(ValueError, match="Missing configuration values"):
        settings_module.validate_settings()


def test_validate_settings_passes_when_required_vars_present(monkeypatch):
    monkeypatch.setenv("KINESIS_STREAM_NAME", "fake-stream")
    monkeypatch.setenv("S3_BUCKET", "fake-bucket")
    monkeypatch.setenv("AWS_REGION", "ca-central-1")

    import config.settings as settings_module

    importlib.reload(settings_module)

    settings_module.validate_settings()  # must not raise
