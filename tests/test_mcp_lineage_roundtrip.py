"""A REAL MCP round trip (stdio, real JSON-RPC, a real subprocess) against a
fake DataHub MCP server whose lineage graph is a genuinely different shape
from reglens/seed/graph.py's Northstar graph — see
tests/fixtures/fake_datahub_mcp_server.py for exactly how.

This is the proof that `reglens.agent.reglens_agent.discover_impact_via_mcp`
now parses whatever the MCP server actually returns, rather than relying on
"the deterministic closure of the same seeded graph" (what the code used to
do: call the MCP server, throw the response away, and return
`discover_impact_deterministic()` regardless). If that old behavior were still
here, this test would return Northstar's 9 downstream assets
(ml.risk_scoring_model, report.regulatory_risk_report, ...) instead of the
fake server's `syn.*` graph, and every assertion below would fail.

No `pytest-asyncio` dependency needed — each test just drives its own asyncio
event loop.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp", reason="mcp is a core requirement (requirements.txt); "
                                         "install it to run the real MCP round trip")

from reglens.agent import mcp_client as mcp_client_module  # noqa: E402
from reglens.agent.mcp_client import DataHubMCP  # noqa: E402
from reglens.agent.reglens_agent import (  # noqa: E402
    ANCHOR,
    discover_impact_deterministic,
    discover_impact_via_mcp,
)
from reglens.seed import graph  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "fake_datahub_mcp_server.py"


def _load_fixture_module():
    """Load the fake server module by path (not as `tests.fixtures....`) so
    this doesn't depend on `tests/` being an importable package."""
    spec = importlib.util.spec_from_file_location("fake_datahub_mcp_server", FIXTURE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


fake_server = _load_fixture_module()


@pytest.fixture()
def fake_mcp_server(monkeypatch):
    """Point DataHubMCP at the fake server subprocess instead of `uvx
    mcp-server-datahub`, using the same interpreter running pytest."""
    monkeypatch.setattr(mcp_client_module, "MCP_COMMAND", sys.executable)
    monkeypatch.setattr(mcp_client_module, "MCP_ARGS", [str(FIXTURE_PATH)])


def _run(coro):
    return asyncio.run(coro)


class TestRealMCPRoundTrip:
    def test_anchor_urn_matches_what_the_real_agent_queries(self):
        # Sanity check that the fixture's anchor identity is not itself a
        # source of drift from the real integration.
        assert fake_server.ANCHOR_URN == graph.dataset_urn(ANCHOR)

    def test_get_lineage_calls_the_real_tool_signature(self, fake_mcp_server):
        # The real DataHub MCP server's get_lineage takes `upstream: bool`, not
        # a `direction` string — this fails loudly (TypeError from the fake
        # server) if DataHubMCP.get_lineage ever regresses to sending the
        # wrong keyword again.
        async def body():
            async with DataHubMCP() as client:
                raw = await client.get_lineage(fake_server.ANCHOR_URN, direction="DOWNSTREAM")
                return DataHubMCP.decode_result(raw)

        decoded = _run(body())
        assert "downstreams" in decoded
        assert decoded["downstreams"]["searchResults"], "expected non-empty downstream results"

    def test_the_agent_s_mcp_path_reflects_the_fake_graph_not_northstar(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        names = [a.name for a in assets]

        # It's the anchor, then the fake server's own graph — not Northstar's.
        assert names[0] == ANCHOR
        fake_names = set(fake_server.NODES)
        assert set(names[1:]) == fake_names, (
            "parser did not faithfully reflect the fake MCP server's actual "
            "downstream results"
        )

        # None of Northstar's real downstream names leaked in — proof this
        # isn't secretly still discover_impact_deterministic().
        northstar_downstream_names = {n.name for n in discover_impact_deterministic()}
        assert not (northstar_downstream_names & fake_names), "graphs must not overlap"
        assert set(names) != northstar_downstream_names
        assert names != [a.name for a in discover_impact_deterministic()]

    def test_fan_out_is_fully_captured(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        names = {a.name for a in assets}
        for branch in ("syn.branch_1", "syn.branch_2", "syn.branch_3", "syn.branch_4", "syn.branch_5"):
            assert branch in names

    def test_the_cycle_terminates_and_both_nodes_appear_exactly_once(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        names = [a.name for a in assets]
        assert names.count("syn.cycle_node_a") == 1
        assert names.count("syn.cycle_node_b") == 1

    def test_the_four_hop_deep_chain_is_reached(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        by_name = {a.name: a for a in assets}
        assert "syn.deepest_chart" in by_name, "max_hops=3 must behave as documented: unlimited"

    def test_entity_types_are_read_from_the_response_not_assumed_uniform(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        by_name = {a.name: a for a in assets}
        assert by_name["syn.model_from_branch_1"].entity_type == "mlModel"
        assert by_name["syn.shared_report"].entity_type == "dashboard"
        assert by_name["syn.deep_pipeline"].entity_type == "dataFlow"
        assert by_name["syn.deepest_chart"].entity_type == "chart"
        assert by_name["syn.branch_1"].entity_type == "dataset"

    def test_names_come_from_properties_name_when_theres_no_top_level_name(self, fake_mcp_server):
        # Only Dataset entities in the fake graph have a top-level "name";
        # Dashboard/MLModel/DataFlow/Chart only have properties.name. If the
        # parser only ever read the top-level field these would be wrong/blank.
        assets = _run(discover_impact_via_mcp())
        by_name = {a.name: a for a in assets}
        assert by_name["syn.shared_report"].name == "syn.shared_report"
        assert by_name["syn.shared_report"].role == "Dashboard fed by both branch 1 and branch 2."

    def test_convergence_keeps_a_single_asset_for_the_shared_child(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        names = [a.name for a in assets]
        assert names.count("syn.shared_report") == 1

    def test_urns_are_the_ones_the_server_actually_returned(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        by_name = {a.name: a for a in assets}
        assert by_name["syn.branch_1"].urn == fake_server._urn("syn.branch_1")

    def test_falls_back_to_the_deterministic_closure_when_the_server_is_unreachable(
        self, monkeypatch
    ):
        monkeypatch.setattr(mcp_client_module, "MCP_COMMAND", "this-binary-does-not-exist-xyz")
        monkeypatch.setattr(mcp_client_module, "MCP_ARGS", [])
        assets = _run(discover_impact_via_mcp())
        assert [a.name for a in assets] == [a.name for a in discover_impact_deterministic()]
