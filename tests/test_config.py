import pytest

from src.config import Config


class TestConfig:
    """Тесты конфигурации."""

    def test_explicit_values(self):
        config = Config(api_id=123, api_hash="abc", bot_token="token", admin_id=456)
        assert config.api_id == 123
        assert config.api_hash == "abc"
        assert config.bot_token == "token"
        assert config.admin_id == 456

    def test_validate_all_present(self):
        config = Config(api_id=123, api_hash="abc", bot_token="token", admin_id=456)
        assert config.validate() == []

    def test_validate_missing_api_id(self):
        config = Config(api_id=0, api_hash="abc", bot_token="token", admin_id=456)
        errors = config.validate()
        assert len(errors) == 1
        assert "API_ID" in errors[0]

    def test_validate_missing_api_hash(self):
        config = Config(api_id=123, api_hash="", bot_token="token", admin_id=456)
        errors = config.validate()
        assert len(errors) == 1
        assert "API_HASH" in errors[0]

    def test_validate_missing_bot_token(self):
        config = Config(api_id=123, api_hash="abc", bot_token="", admin_id=456)
        errors = config.validate()
        assert len(errors) == 1
        assert "BOT_TOKEN" in errors[0]

    def test_validate_missing_admin_id(self):
        config = Config(api_id=123, api_hash="abc", bot_token="token", admin_id=0)
        errors = config.validate()
        assert len(errors) == 1
        assert "ADMIN_ID" in errors[0]

    def test_validate_all_missing(self):
        config = Config(api_id=0, api_hash="", bot_token="", admin_id=0)
        errors = config.validate()
        assert len(errors) == 4

    def test_defaults_from_env(self, monkeypatch):
        monkeypatch.setenv("API_ID", "999")
        monkeypatch.setenv("API_HASH", "testhash")
        monkeypatch.setenv("BOT_TOKEN", "testtoken")
        monkeypatch.setenv("ADMIN_ID", "888")
        config = Config()
        assert config.api_id == 999
        assert config.api_hash == "testhash"
        assert config.bot_token == "testtoken"
        assert config.admin_id == 888
