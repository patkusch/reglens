"""Config is read from the environment when the module loads, so each test reloads it."""
import importlib

import pytest

from reglens import config

KEYS = ["DATAHUB_GMS_URL", "DATAHUB_TOKEN", "MCP_COMMAND", "MCP_ARGS", "TOOLS_IS_MUTATION_ENABLED",
        "ANTHROPIC_API_KEY", "BANK_PLATFORM"]


@pytest.fixture
def fresh(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)

    def load(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        return importlib.reload(config)

    yield load
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    importlib.reload(config)


def test_defaults_work_with_nothing_set(fresh):
    c = fresh()
    assert c.DATAHUB_GMS_URL == "http://localhost:8080"
    assert c.DATAHUB_TOKEN == ""
    assert c.MCP_COMMAND == "uvx"
    assert c.MCP_ARGS == ["mcp-server-datahub"]
    assert c.BANK_PLATFORM == "snowflake"
    assert c.BANK_ENV == "PROD"


def test_the_model_key_is_empty_by_default_so_the_core_loop_runs_without_one(fresh):
    assert fresh().ANTHROPIC_API_KEY == ""


def test_writing_back_to_the_graph_is_on_by_default(fresh):
    assert fresh().MCP_MUTATION_ENABLED == "true"


def test_environment_values_replace_the_defaults(fresh):
    c = fresh(DATAHUB_GMS_URL="http://datahub.internal:9002", DATAHUB_TOKEN="t0k", BANK_PLATFORM="bigquery",
              TOOLS_IS_MUTATION_ENABLED="false", ANTHROPIC_API_KEY="sk-test")
    assert c.DATAHUB_GMS_URL == "http://datahub.internal:9002"
    assert c.DATAHUB_TOKEN == "t0k"
    assert c.BANK_PLATFORM == "bigquery"
    assert c.MCP_MUTATION_ENABLED == "false"
    assert c.ANTHROPIC_API_KEY == "sk-test"


def test_mcp_arguments_are_split_on_spaces(fresh):
    c = fresh(MCP_ARGS="run --quiet mcp-server-datahub")
    assert c.MCP_ARGS == ["run", "--quiet", "mcp-server-datahub"]
