"""Tests for org config loading and env var substitution."""
import os
import pytest
from pathlib import Path
from unittest.mock import patch

from agent.core.org_config import (
    OrgConfig, LLMConfig, StorageConfig, ChatConfig,
    _substitute_env_vars, _substitute_recursively,
    load_org_configs, get_org_config, clear_org_configs,
)


class TestEnvVarSubstitution:
    """Test ${VAR} substitution in config values."""

    def test_substitutes_env_var(self):
        with patch.dict(os.environ, {"MY_KEY": "secret123"}):
            assert _substitute_env_vars("${MY_KEY}") == "secret123"

    def test_substitutes_multiple_vars(self):
        with patch.dict(os.environ, {"A": "hello", "B": "world"}):
            assert _substitute_env_vars("${A}-${B}") == "hello-world"

    def test_missing_var_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            result = _substitute_env_vars("${NONEXISTENT_VAR}")
            assert result == ""

    def test_no_vars_unchanged(self):
        assert _substitute_env_vars("plain text") == "plain text"

    def test_recursive_substitution_in_dict(self):
        with patch.dict(os.environ, {"KEY": "val"}):
            data = {"a": "${KEY}", "b": {"c": "${KEY}"}}
            result = _substitute_recursively(data)
            assert result == {"a": "val", "b": {"c": "val"}}

    def test_recursive_substitution_in_list(self):
        with patch.dict(os.environ, {"X": "y"}):
            data = ["${X}", "plain"]
            result = _substitute_recursively(data)
            assert result == ["y", "plain"]

    def test_non_string_passthrough(self):
        assert _substitute_recursively(42) == 42
        assert _substitute_recursively(None) is None
        assert _substitute_recursively(True) is True


class TestOrgConfigModel:
    """Test OrgConfig pydantic model validation."""

    def test_minimal_config(self):
        config = OrgConfig(llm=LLMConfig(provider="gemini", api_key="key"))
        assert config.timezone == "America/Los_Angeles"
        assert config.storage.backend == "grist"
        assert config.chat.platform == "discord"

    def test_full_config(self):
        config = OrgConfig(
            name="Test Org",
            timezone="America/New_York",
            llm=LLMConfig(
                provider="openai_compatible",
                api_key="hf-key",
                model="PleIAs/pleias-large",
                endpoint_url="https://api-inference.huggingface.co/v1",
            ),
            storage=StorageConfig(
                backend="grist",
                api_key="grist-key",
                doc_id="doc123",
            ),
            chat=ChatConfig(
                platform="slack",
                channels=["C012345"],
            ),
        )
        assert config.name == "Test Org"
        assert config.llm.provider == "openai_compatible"
        assert config.llm.endpoint_url == "https://api-inference.huggingface.co/v1"
        assert config.chat.platform == "slack"

    def test_llm_config_requires_provider_and_key(self):
        with pytest.raises(Exception):
            LLMConfig()


class TestLoadOrgConfigs:
    """Test YAML loading and fallback behavior."""

    def setup_method(self):
        clear_org_configs()

    def teardown_method(self):
        clear_org_configs()

    def test_loads_from_yaml(self, tmp_path):
        yaml_content = """\
orgs:
  test_org:
    name: "Test"
    timezone: "America/New_York"
    llm:
      provider: "gemini"
      api_key: "test-api-key"
      model: "gemini-2.5-flash-lite"
"""
        config_file = tmp_path / "orgs.yaml"
        config_file.write_text(yaml_content)

        configs = load_org_configs(config_file)
        assert "test_org" in configs
        assert configs["test_org"].name == "Test"
        assert configs["test_org"].llm.api_key == "test-api-key"

    def test_env_var_substitution_in_yaml(self, tmp_path):
        yaml_content = """\
orgs:
  sub_test:
    llm:
      provider: "gemini"
      api_key: "${TEST_GEMINI_KEY}"
"""
        config_file = tmp_path / "orgs.yaml"
        config_file.write_text(yaml_content)

        with patch.dict(os.environ, {"TEST_GEMINI_KEY": "resolved-key"}):
            configs = load_org_configs(config_file)
            assert configs["sub_test"].llm.api_key == "resolved-key"

    def test_fallback_to_env_vars(self, tmp_path):
        """When no YAML exists, builds default config from env vars."""
        nonexistent = tmp_path / "does_not_exist.yaml"
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"}):
            configs = load_org_configs(nonexistent)
            assert "orb" in configs
            assert configs["orb"].llm.provider == "gemini"
            assert configs["orb"].llm.api_key == "env-key"

    def test_invalid_org_raises(self, tmp_path):
        yaml_content = """\
orgs:
  bad_org:
    name: "Missing LLM"
"""
        config_file = tmp_path / "orgs.yaml"
        config_file.write_text(yaml_content)

        with pytest.raises(Exception):
            load_org_configs(config_file)


class TestGetOrgConfig:
    """Test org config lookup."""

    def setup_method(self):
        clear_org_configs()

    def teardown_method(self):
        clear_org_configs()

    def test_default_returns_first_org(self, tmp_path):
        yaml_content = """\
orgs:
  first:
    name: "First"
    llm:
      provider: "gemini"
      api_key: "key1"
  second:
    name: "Second"
    llm:
      provider: "gemini"
      api_key: "key2"
"""
        config_file = tmp_path / "orgs.yaml"
        config_file.write_text(yaml_content)
        load_org_configs(config_file)

        config = get_org_config("default")
        assert config.name == "First"

    def test_specific_org_lookup(self, tmp_path):
        yaml_content = """\
orgs:
  org_a:
    name: "Org A"
    llm:
      provider: "gemini"
      api_key: "key-a"
  org_b:
    name: "Org B"
    llm:
      provider: "openai_compatible"
      api_key: "key-b"
      endpoint_url: "https://example.com/v1"
      model: "test-model"
"""
        config_file = tmp_path / "orgs.yaml"
        config_file.write_text(yaml_content)
        load_org_configs(config_file)

        config = get_org_config("org_b")
        assert config.name == "Org B"
        assert config.llm.provider == "openai_compatible"

    def test_unknown_org_raises(self, tmp_path):
        yaml_content = """\
orgs:
  only_org:
    llm:
      provider: "gemini"
      api_key: "key"
"""
        config_file = tmp_path / "orgs.yaml"
        config_file.write_text(yaml_content)
        load_org_configs(config_file)

        with pytest.raises(ValueError, match="Unknown org_id"):
            get_org_config("nonexistent")
