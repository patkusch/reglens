"""The optional MCP write-back helpers, against a fake DataHub MCP server that
exposes the REAL `update_description` and `add_terms` tools (signatures quoted from
acryldata/mcp-server-datahub in reglens/agent/mcp_client.py) and rejects any argument
name those tools do not have.

The helpers used to call `update_description(urn=..., description=...)` and look for a
glossary tool by keyword. The real tools take `entity_urn`, and the glossary tool is
registered as `add_terms` taking `term_urns` and `entity_urns`, so against a real
server the old code either sent rejected arguments or found no tool at all. The
fake server refuses those calls the way the real one would; nothing here has ever
run against a live DataHub.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="mcp is a core requirement (requirements.txt)")

from reglens.agent import mcp_client as mcp_client_module  # noqa: E402
from reglens.agent.mcp_client import DataHubMCP, MutationToolsUnavailable  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "fake_datahub_mcp_server.py"

DATASET = "urn:li:dataset:(urn:li:dataPlatform:snowflake,risk.customer_risk_profile,PROD)"
DASHBOARD = "urn:li:dashboard:(powerbi,dash.risk_committee_report)"
TERM = "urn:li:glossaryTerm:RegLens.RCS-2026.ACT_NOW"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def fake_mcp_server(monkeypatch):
    monkeypatch.setattr(mcp_client_module, "MCP_COMMAND", sys.executable)
    monkeypatch.setattr(mcp_client_module, "MCP_ARGS", [str(FIXTURE_PATH)])


@pytest.fixture()
def recorded(monkeypatch, tmp_path, fake_mcp_server):
    """Turn on the fake server's call log and return a function that reads it."""
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_DATAHUB_RECORD", str(log))
    monkeypatch.setenv("FAKE_DATAHUB_KNOWN_TERMS", TERM)

    def read() -> list[dict]:
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    return read


def _is_error(res) -> bool:
    # `is_error` on mcp>=2, `isError` on mcp<2.
    flag = getattr(res, "is_error", None)
    return bool(getattr(res, "isError", False) if flag is None else flag)


def _text(res) -> str:
    return " ".join(getattr(b, "text", "") or "" for b in res.content)


class TestRealSignatures:
    def test_the_fake_advertises_the_real_tool_signatures(self, fake_mcp_server):
        async def body():
            async with DataHubMCP() as client:
                tools = await client._session.list_tools()
                return {
                    t.name: getattr(t, "inputSchema", None) or t.input_schema
                    for t in tools.tools
                }

        schemas = _run(body())

        upd = schemas["update_description"]
        assert set(upd["properties"]) == {"entity_urn", "operation", "description", "column_path"}
        assert upd["required"] == ["entity_urn"]
        assert set(upd["properties"]["operation"]["enum"]) == {"replace", "append", "remove"}

        terms = schemas["add_terms"]
        assert set(terms["properties"]) == {"term_urns", "entity_urns", "column_paths"}
        assert sorted(terms["required"]) == ["entity_urns", "term_urns"]
        assert terms["properties"]["term_urns"]["type"] == "array"
        assert terms["properties"]["entity_urns"]["type"] == "array"

        # The Python function is `add_glossary_terms`, but the server registers it as
        # `add_terms`; nothing by the old name exists.
        assert "add_glossary_terms" not in schemas
        assert "add_glossary_term" not in schemas


class TestCorrectCallsSucceed:
    def test_update_description_sends_entity_urn_and_the_server_records_it(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.update_description(DATASET, "Assessed: ACT_NOW.")

        result = _run(body())
        assert result["success"] is True
        assert result["urn"] == DATASET
        assert recorded() == [{
            "tool": "update_description",
            "arguments": {
                "entity_urn": DATASET, "operation": "replace",
                "description": "Assessed: ACT_NOW.", "column_path": None,
            },
        }]

    def test_update_description_can_append_to_a_column(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.update_description(
                    DATASET, " (PII)", operation="append", column_path="email"
                )

        assert _run(body())["column_path"] == "email"
        (call,) = recorded()
        assert call["arguments"] == {
            "entity_urn": DATASET, "operation": "append",
            "description": " (PII)", "column_path": "email",
        }

    def test_update_description_remove_needs_no_description(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.update_description(DATASET, None, operation="remove")

        assert "removed" in _run(body())["message"]
        assert recorded()[0]["arguments"]["description"] is None

    def test_add_glossary_terms_sends_term_urns_and_entity_urns(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.add_glossary_terms([TERM], [DATASET, DASHBOARD])

        result = _run(body())
        assert result["success"] is True
        assert recorded() == [{
            "tool": "add_terms",
            "arguments": {
                "term_urns": [TERM], "entity_urns": [DATASET, DASHBOARD], "column_paths": None,
            },
        }]

    def test_add_glossary_term_turns_a_bare_name_into_a_term_urn(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.add_glossary_term(DATASET, "RegLens.RCS-2026.ACT_NOW")

        assert _run(body())["success"] is True
        (call,) = recorded()
        assert call["arguments"]["term_urns"] == [TERM]
        assert call["arguments"]["entity_urns"] == [DATASET]

    def test_add_glossary_term_leaves_a_full_term_urn_alone(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.add_glossary_term(DATASET, TERM)

        _run(body())
        assert recorded()[0]["arguments"]["term_urns"] == [TERM]


class TestOldWrongCallsAreRejected:
    """The argument names and tool name the helpers used to send. These go through
    the raw `call`, so they show what the server does with them."""

    def test_update_description_with_urn_instead_of_entity_urn(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.call("update_description", urn=DATASET, description="x")

        res = _run(body())
        assert _is_error(res)
        assert "urn" in _text(res) and "Unexpected keyword" in _text(res)
        assert recorded() == [], "a rejected call must not reach the tool body"

    def test_add_terms_with_urn_and_term_instead_of_the_real_names(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.call("add_terms", urn=DATASET, term="RegLens.X")

        res = _run(body())
        assert _is_error(res)
        assert "Unexpected keyword" in _text(res)
        assert recorded() == []

    def test_a_valid_call_plus_one_unknown_name_is_still_rejected(self, recorded):
        # Not just "required argument missing": an extra name is refused on its own.
        async def body():
            async with DataHubMCP() as client:
                return await client.call(
                    "update_description", entity_urn=DATASET, description="x", note="y"
                )

        res = _run(body())
        assert _is_error(res)
        assert "note" in _text(res)
        assert recorded() == []

    def test_the_old_glossary_tool_name_does_not_exist_on_the_server(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.call(
                    "add_glossary_terms", term_urns=[TERM], entity_urns=[DATASET]
                )

        res = _run(body())
        assert _is_error(res)
        assert recorded() == []

    def test_a_term_that_does_not_exist_is_a_clear_error_not_a_silent_success(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.add_glossary_term(DATASET, "RegLens.NotCreated.ACT_NOW")

        with pytest.raises(RuntimeError, match="do not exist in DataHub"):
            _run(body())
        assert recorded() == []

    def test_an_empty_description_is_a_clear_error(self, recorded):
        async def body():
            async with DataHubMCP() as client:
                return await client.update_description(DATASET, "")

        with pytest.raises(RuntimeError, match="description is required"):
            _run(body())
        assert recorded() == []


class TestServerWithoutMutationTools:
    @pytest.fixture()
    def read_only_server(self, monkeypatch, fake_mcp_server, tmp_path):
        # The same switch the real server has: mutation tools are only registered
        # when TOOLS_IS_MUTATION_ENABLED is true. `_server_params` passes it on.
        monkeypatch.setattr(mcp_client_module, "MCP_MUTATION_ENABLED", "false")
        log = tmp_path / "calls.jsonl"
        monkeypatch.setenv("FAKE_DATAHUB_RECORD", str(log))
        return log

    def test_the_tools_are_absent_from_list_tools(self, read_only_server):
        async def body():
            async with DataHubMCP() as client:
                return client.tool_names

        names = _run(body())
        assert "get_lineage" in names
        assert "update_description" not in names and "add_terms" not in names

    def test_update_description_raises_a_clear_error(self, read_only_server):
        async def body():
            async with DataHubMCP() as client:
                await client.update_description(DATASET, "x")

        with pytest.raises(MutationToolsUnavailable) as err:
            _run(body())
        msg = str(err.value)
        assert "update_description" in msg
        assert "TOOLS_IS_MUTATION_ENABLED=true" in msg
        assert "get_lineage" in msg, "the message should list what the server did expose"
        assert not read_only_server.exists()

    def test_add_glossary_term_raises_a_clear_error(self, read_only_server):
        async def body():
            async with DataHubMCP() as client:
                await client.add_glossary_term(DATASET, "RegLens.RCS-2026.ACT_NOW")

        with pytest.raises(MutationToolsUnavailable, match="add_terms"):
            _run(body())
        assert not read_only_server.exists()

    def test_it_is_a_runtime_error_so_existing_handlers_still_catch_it(self, read_only_server):
        async def body():
            async with DataHubMCP() as client:
                await client.add_glossary_terms([TERM], [DATASET])

        with pytest.raises(RuntimeError):
            _run(body())

    def test_reads_still_work_on_the_read_only_server(self, read_only_server):
        async def body():
            async with DataHubMCP() as client:
                return DataHubMCP.decode_result(await client.get_lineage(DATASET))

        assert "downstreams" in _run(body())
