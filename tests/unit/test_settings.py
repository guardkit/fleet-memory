"""Unit tests for fleet_memory.settings.Settings configuration."""

import os

import pytest
from pydantic import ValidationError

from fleet_memory.settings import Settings


class TestSettingsValidation:
    """Test Settings validation and required field handling."""

    def test_missing_all_required_fields_names_each_field(self, monkeypatch) -> None:
        """Missing required fields should raise ValidationError naming each missing field."""
        # Clear any existing FLEET_MEMORY_ env vars
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        # Check that both required fields are mentioned in the error
        assert "pg_dsn" in error_msg.lower()
        assert "embed_url" in error_msg.lower()

    def test_missing_pg_dsn_only(self, monkeypatch) -> None:
        """Missing only pg_dsn should raise ValidationError naming pg_dsn."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://localhost:9000")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "pg_dsn" in error_msg.lower()

    def test_missing_embed_url_only(self, monkeypatch) -> None:
        """Missing only embed_url should raise ValidationError naming embed_url."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://u:p@localhost/db")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "embed_url" in error_msg.lower()

    def test_empty_string_pg_dsn_raises_validation_error(self, monkeypatch) -> None:
        """Empty-string FLEET_MEMORY_PG_DSN should raise ValidationError."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://localhost:9000")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "pg_dsn" in error_msg.lower()
        assert "cannot be empty" in error_msg.lower()

    def test_whitespace_only_pg_dsn_raises_validation_error(self, monkeypatch) -> None:
        """Whitespace-only FLEET_MEMORY_PG_DSN should raise ValidationError."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "   ")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://localhost:9000")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "pg_dsn" in error_msg.lower()
        assert "cannot be empty" in error_msg.lower()

    def test_empty_string_embed_url_raises_validation_error(self, monkeypatch) -> None:
        """Empty-string FLEET_MEMORY_EMBED_URL should raise ValidationError."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://u:p@localhost/db")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "embed_url" in error_msg.lower()
        assert "cannot be empty" in error_msg.lower()

    def test_whitespace_only_embed_url_raises_validation_error(self, monkeypatch) -> None:
        """Whitespace-only FLEET_MEMORY_EMBED_URL should raise ValidationError."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://u:p@localhost/db")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "   ")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "embed_url" in error_msg.lower()
        assert "cannot be empty" in error_msg.lower()


class TestSettingsDefaults:
    """Test that all default values match documented placeholders."""

    def test_all_defaults_match_documented_values(self, monkeypatch) -> None:
        """All defaults should match the values documented in .env.example."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://u:p@localhost/db")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://localhost:9000")

        settings = Settings()

        # Verify defaults match .env.example documented placeholders
        assert settings.embed_model == "nomic-embed-text-v1.5"
        assert settings.embed_dims == 768
        assert settings.embed_timeout_s == 10.0  # ASSUM-008
        assert settings.pg_pool_min == 2
        assert settings.pg_pool_max == 10  # ASSUM-004
        assert settings.pg_connect_timeout_s == 10.0  # ASSUM-006
        assert settings.nats_url == "nats://localhost:4222"

    def test_defaults_when_only_required_fields_provided(self, monkeypatch) -> None:
        """When only required fields are provided, defaults should be applied."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://test:test@localhost/test")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://embed.example.com")

        settings = Settings()

        assert settings.pg_dsn == "postgresql://test:test@localhost/test"
        assert settings.embed_url == "http://embed.example.com"
        assert settings.embed_model == "nomic-embed-text-v1.5"
        assert settings.embed_dims == 768
        assert settings.embed_timeout_s == 10.0
        assert settings.pg_pool_min == 2
        assert settings.pg_pool_max == 10
        assert settings.pg_connect_timeout_s == 10.0
        assert settings.nats_url == "nats://localhost:4222"


class TestSettingsPrefixIsolation:
    """Test FLEET_MEMORY_ prefix isolation - unprefixed env vars should be ignored."""

    def test_unprefixed_pg_dsn_is_ignored(self, monkeypatch) -> None:
        """Unprefixed PG_DSN environment variable should be ignored."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        # Set unprefixed env var
        monkeypatch.setenv("PG_DSN", "postgresql://wrong:wrong@localhost/wrong")
        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://correct:correct@localhost/correct")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://localhost:9000")

        settings = Settings()

        # Should use the prefixed version, not the unprefixed one
        assert settings.pg_dsn == "postgresql://correct:correct@localhost/correct"
        assert "wrong" not in settings.pg_dsn

    def test_unprefixed_embed_url_is_ignored(self, monkeypatch) -> None:
        """Unprefixed EMBED_URL environment variable should be ignored."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        # Set unprefixed env var
        monkeypatch.setenv("EMBED_URL", "http://wrong:9999")
        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://u:p@localhost/db")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://correct:9000")

        settings = Settings()

        # Should use the prefixed version
        assert settings.embed_url == "http://correct:9000"
        assert "wrong" not in settings.embed_url

    def test_unprefixed_optional_fields_ignored(self, monkeypatch) -> None:
        """Unprefixed optional field env vars should be ignored, defaults used instead."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        # Set unprefixed env vars that should be ignored
        monkeypatch.setenv("NATS_URL", "nats://wrong:4223")
        monkeypatch.setenv("EMBED_MODEL", "wrong-model")
        monkeypatch.setenv("PG_POOL_MAX", "999")

        # Set only required prefixed vars
        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://u:p@localhost/db")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://localhost:9000")

        settings = Settings()

        # Should use defaults, not unprefixed env vars
        assert settings.nats_url == "nats://localhost:4222"
        assert settings.embed_model == "nomic-embed-text-v1.5"
        assert settings.pg_pool_max == 10


class TestSettingsEnvPrecedence:
    """Test that OS env vars take precedence over .env file values (risk R6)."""

    def test_os_env_overrides_env_file(self, monkeypatch, tmp_path) -> None:
        """OS environment variables should take precedence over .env file values."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        # Create a .env file with values
        env_file = tmp_path / ".env"
        env_file.write_text(
            "FLEET_MEMORY_PG_DSN=postgresql://file:file@localhost/file_db\n"
            "FLEET_MEMORY_EMBED_URL=http://file:8888\n"
            "FLEET_MEMORY_PG_POOL_MAX=20\n"
        )

        # Change to tmp directory so .env file is found
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Set OS env vars that should override .env file
            monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://os:os@localhost/os_db")
            monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://os:9999")

            settings = Settings()

            # OS env should take precedence
            assert settings.pg_dsn == "postgresql://os:os@localhost/os_db"
            assert settings.embed_url == "http://os:9999"
            # Value from .env should be used if not in OS env
            assert settings.pg_pool_max == 20
        finally:
            os.chdir(original_cwd)

    def test_env_file_used_when_no_os_env(self, monkeypatch, tmp_path) -> None:
        """.env file values should be used when OS env vars are not set."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        # Create a .env file with all values
        env_file = tmp_path / ".env"
        env_file.write_text(
            "FLEET_MEMORY_PG_DSN=postgresql://file:file@localhost/file_db\n"
            "FLEET_MEMORY_EMBED_URL=http://file:8888\n"
            "FLEET_MEMORY_PG_POOL_MAX=25\n"
            "FLEET_MEMORY_NATS_URL=nats://file:4223\n"
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            settings = Settings()

            # All values should come from .env file
            assert settings.pg_dsn == "postgresql://file:file@localhost/file_db"
            assert settings.embed_url == "http://file:8888"
            assert settings.pg_pool_max == 25
            assert settings.nats_url == "nats://file:4223"
        finally:
            os.chdir(original_cwd)


class TestSettingsNoForbiddenImports:
    """Verify that settings.py contains no forbidden imports."""

    def test_settings_module_has_no_nats_imports(self) -> None:
        """settings.py should not import NATS."""
        import sys

        import fleet_memory.settings as settings_module

        # Check if any NATS-related modules are imported
        nats_modules = [name for name in sys.modules.keys() if "nats" in name.lower()]
        # If NATS modules exist, they should not be imported by settings module
        if nats_modules:
            settings_source = settings_module.__file__
            with open(settings_source) as f:
                source_code = f.read()
            assert "import nats" not in source_code.lower()
            assert "from nats" not in source_code.lower()

    def test_settings_module_has_no_httpx_imports(self) -> None:
        """settings.py should not import httpx."""
        import fleet_memory.settings as settings_module

        settings_source = settings_module.__file__
        with open(settings_source) as f:
            source_code = f.read()
        assert "import httpx" not in source_code.lower()
        assert "from httpx" not in source_code.lower()

    def test_settings_module_has_no_psycopg_imports(self) -> None:
        """settings.py should not import psycopg."""
        import fleet_memory.settings as settings_module

        settings_source = settings_module.__file__
        with open(settings_source) as f:
            source_code = f.read()
        assert "import psycopg" not in source_code.lower()
        assert "from psycopg" not in source_code.lower()


class TestSettingsIntegration:
    """Integration tests for Settings with realistic configurations."""

    def test_ac001_verification_command(self, monkeypatch) -> None:
        """Verify AC-001 command works: instantiate Settings with required fields."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://u:p@localhost/db")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://localhost:9000")

        s = Settings()

        # Verify the assertions from AC-001
        assert s.pg_pool_max == 10
        assert s.embed_timeout_s == 10.0
        assert s.pg_connect_timeout_s == 10.0

    def test_realistic_mac_dev_config(self, monkeypatch) -> None:
        """Test with realistic mac-dev configuration from .env.example."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        # Set values from .env.example mac-dev block
        monkeypatch.setenv(
            "FLEET_MEMORY_PG_DSN",
            "postgresql://fleet_user:fleet_pass@localhost:5432/fleet_memory",
        )
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://localhost:9000")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_MODEL", "nomic-embed-text-v1.5")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_DIMS", "768")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_TIMEOUT_S", "10.0")
        monkeypatch.setenv("FLEET_MEMORY_PG_POOL_MIN", "2")
        monkeypatch.setenv("FLEET_MEMORY_PG_POOL_MAX", "10")
        monkeypatch.setenv("FLEET_MEMORY_PG_CONNECT_TIMEOUT_S", "10.0")
        monkeypatch.setenv("FLEET_MEMORY_NATS_URL", "nats://localhost:4222")

        settings = Settings()

        assert settings.pg_dsn == "postgresql://fleet_user:fleet_pass@localhost:5432/fleet_memory"
        assert settings.embed_url == "http://localhost:9000"
        assert settings.embed_model == "nomic-embed-text-v1.5"
        assert settings.embed_dims == 768
        assert settings.embed_timeout_s == 10.0
        assert settings.pg_pool_min == 2
        assert settings.pg_pool_max == 10
        assert settings.pg_connect_timeout_s == 10.0
        assert settings.nats_url == "nats://localhost:4222"

    def test_custom_override_values(self, monkeypatch) -> None:
        """Test that custom values can override defaults."""
        for key in list(os.environ.keys()):
            if key.startswith("FLEET_MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://custom:custom@db:5432/custom")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://custom-embed:8080")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_MODEL", "custom-model-v2")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_DIMS", "1024")
        monkeypatch.setenv("FLEET_MEMORY_EMBED_TIMEOUT_S", "30.0")
        monkeypatch.setenv("FLEET_MEMORY_PG_POOL_MIN", "5")
        monkeypatch.setenv("FLEET_MEMORY_PG_POOL_MAX", "50")
        monkeypatch.setenv("FLEET_MEMORY_PG_CONNECT_TIMEOUT_S", "20.0")
        monkeypatch.setenv("FLEET_MEMORY_NATS_URL", "nats://custom-nats:4222")

        settings = Settings()

        assert settings.pg_dsn == "postgresql://custom:custom@db:5432/custom"
        assert settings.embed_url == "http://custom-embed:8080"
        assert settings.embed_model == "custom-model-v2"
        assert settings.embed_dims == 1024
        assert settings.embed_timeout_s == 30.0
        assert settings.pg_pool_min == 5
        assert settings.pg_pool_max == 50
        assert settings.pg_connect_timeout_s == 20.0
        assert settings.nats_url == "nats://custom-nats:4222"
