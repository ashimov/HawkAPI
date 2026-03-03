"""Tests for Settings and env configuration."""

import pytest

from hawkapi.config.env import load_dotenv
from hawkapi.config.profiles import load_profile_env
from hawkapi.config.settings import Settings, _coerce, env_field


class TestLoadDotenv:
    def test_parses_key_value(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\nBAZ=42\n")
        result = load_dotenv(env_file)
        assert result == {"FOO": "bar", "BAZ": "42"}

    def test_strips_quotes(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("DB_URL=\"postgres://localhost\"\nSECRET='s3cret'\n")
        result = load_dotenv(env_file)
        assert result["DB_URL"] == "postgres://localhost"
        assert result["SECRET"] == "s3cret"

    def test_skips_comments_and_blank(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# This is a comment\n\nKEY=value\n")
        result = load_dotenv(env_file)
        assert result == {"KEY": "value"}

    def test_missing_file_returns_empty(self, tmp_path):
        result = load_dotenv(tmp_path / "nonexistent")
        assert result == {}

    def test_no_equals_line_skipped(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("INVALID_LINE\nGOOD=value\n")
        result = load_dotenv(env_file)
        assert result == {"GOOD": "value"}


class TestLoadProfileEnv:
    def test_base_env_loaded(self, tmp_path):
        (tmp_path / ".env").write_text("APP_NAME=myapp\n")
        result = load_profile_env("development", base_dir=tmp_path)
        assert result["APP_NAME"] == "myapp"

    def test_profile_overrides_base(self, tmp_path):
        (tmp_path / ".env").write_text("DEBUG=false\n")
        (tmp_path / ".env.production").write_text("DEBUG=true\n")
        result = load_profile_env("production", base_dir=tmp_path)
        assert result["DEBUG"] == "true"

    def test_real_env_overrides_file(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("MY_VAR=from_file\n")
        monkeypatch.setenv("MY_VAR", "from_env")
        result = load_profile_env("development", base_dir=tmp_path)
        assert result["MY_VAR"] == "from_env"

    def test_defaults_to_development(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HAWK_ENV", raising=False)
        (tmp_path / ".env.development").write_text("MODE=dev\n")
        result = load_profile_env(base_dir=tmp_path)
        assert result.get("MODE") == "dev"


class TestCoerce:
    def test_bool_true_values(self):
        for val in ("true", "1", "yes", "on", "True", "YES"):
            assert _coerce(val, bool) is True

    def test_bool_false_values(self):
        for val in ("false", "0", "no", "off"):
            assert _coerce(val, bool) is False

    def test_int(self):
        assert _coerce("42", int) == 42

    def test_float(self):
        assert _coerce("3.14", float) == 3.14

    def test_str(self):
        assert _coerce(42, str) == "42"

    def test_list_from_csv(self):
        assert _coerce("a, b, c", list) == ["a", "b", "c"]

    def test_already_correct_type(self):
        assert _coerce(42, int) == 42


class TestSettings:
    def test_load_from_env(self, monkeypatch):
        class AppSettings(Settings):
            db_url: str = env_field("DATABASE_URL")
            debug: bool = env_field("DEBUG", default=False)
            port: int = env_field("PORT", default=8000)

        monkeypatch.setenv("DATABASE_URL", "postgres://localhost/test")
        settings = AppSettings.load()
        assert settings.db_url == "postgres://localhost/test"
        assert settings.debug is False
        assert settings.port == 8000

    def test_load_from_dotenv(self, tmp_path):
        (tmp_path / ".env").write_text("MY_DB=sqlite:///test.db\n")

        class AppSettings(Settings):
            db: str = env_field("MY_DB")

        settings = AppSettings.load(base_dir=tmp_path)
        assert settings.db == "sqlite:///test.db"

    def test_overrides_win(self, monkeypatch):
        class AppSettings(Settings):
            port: int = env_field("PORT", default=8000)

        monkeypatch.setenv("PORT", "9000")
        settings = AppSettings.load(port=3000)
        assert settings.port == 3000

    def test_missing_required_raises(self, monkeypatch):
        class AppSettings(Settings):
            secret: str = env_field("TOP_SECRET")

        monkeypatch.delenv("TOP_SECRET", raising=False)

        with pytest.raises(ValueError, match="Required setting"):
            AppSettings.load(base_dir="/tmp/empty_" + str(id(self)))

    def test_repr_masks_secrets(self, monkeypatch):
        class AppSettings(Settings):
            api_key: str = env_field("API_KEY", default="real-key")
            name: str = env_field("APP_NAME", default="test")

        settings = AppSettings.load()
        r = repr(settings)
        assert "***" in r
        assert "real-key" not in r
        assert "test" in r
