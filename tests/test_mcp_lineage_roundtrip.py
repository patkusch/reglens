"""A REAL MCP round trip (stdio, real JSON-RPC, a real subprocess) against a
fake DataHub MCP server whose lineage graph is a genuinely different shape
from reglens/seed/graph.py's Northstar graph — see
tests/fixtures/fake_datahub_mcp_server.py for exactly how.

This is the proof that `reglens.agent.reglens_agent.discover_impact_via_mcp`
now parses whatever the MCP server actually returns, rather than relying on
"the deterministic closure of the same seeded graph" (what the code used to
do: call the MCP server, throw the response away, and return
`discover_impact_deterministic()` regardless). If that old behavior were still
here, this test would return Northstar's downstream assets
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
    build_assessment,
    discover_impact_deterministic,
    discover_impact_via_mcp,
)
from reglens.engine import scenario_engine as se  # noqa: E402
from reglens.engine.impact_card import writeback_payload  # noqa: E402
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

    def test_the_six_hop_deep_chain_is_reached(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        by_name = {a.name: a for a in assets}
        assert "syn.exec_view" in by_name, "max_hops=3 must behave as documented: unlimited"

    def test_a_mixed_type_closure_comes_back_with_the_right_kinds_and_urns(self, fake_mcp_server):
        # Written out by hand, not derived from the fixture's own helpers, so a
        # wrong URN form in the fixture can't quietly agree with itself.
        expected = {
            "syn.branch_1": ("dataset", "urn:li:dataset:(urn:li:dataPlatform:snowflake,syn.branch_1,PROD)"),
            "syn.scored_output": ("dataset", "urn:li:dataset:(urn:li:dataPlatform:snowflake,syn.scored_output,PROD)"),
            "syn.scorer_v1": ("mlModel", "urn:li:mlModel:(urn:li:dataPlatform:mlflow,syn.scorer_v1,PROD)"),
            "syn.shared_view": ("dashboard", "urn:li:dashboard:(powerbi,syn.shared_view)"),
            "syn.exec_view": ("dashboard", "urn:li:dashboard:(powerbi,syn.exec_view)"),
            "syn.train_job": ("dataJob", "urn:li:dataJob:(urn:li:dataFlow:(airflow,syn.train_job,PROD),syn.train_job)"),
            "syn.scoring_job": ("dataJob", "urn:li:dataJob:(urn:li:dataFlow:(airflow,syn.scoring_job,PROD),syn.scoring_job)"),
            "syn.chart_4": ("chart", "urn:li:chart:(looker,syn.chart_4)"),
        }
        assets = _run(discover_impact_via_mcp())
        by_name = {a.name: a for a in assets}
        for name, (kind, urn) in expected.items():
            assert (by_name[name].entity_type, by_name[name].urn) == (kind, urn), name

    def test_every_assets_kind_is_the_entity_type_in_its_own_urn(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        kinds = set()
        for a in assets:
            assert a.urn.startswith(f"urn:li:{a.entity_type}:"), (a.name, a.urn, a.entity_type)
            kinds.add(a.entity_type)
        assert kinds == {"dataset", "dashboard", "mlModel", "dataJob", "chart"}

    def test_a_dataset_tagged_dashboard_is_still_a_dataset(self, fake_mcp_server):
        # The old seed marked dashboards as datasets with a "Dashboard" subtype tag.
        # The server sends that tag on this dataset; the URN says dataset, so it is one.
        assets = _run(discover_impact_via_mcp())
        by_name = {a.name: a for a in assets}
        assert by_name["syn.tagged_dashboard"].entity_type == "dataset"

    def test_names_and_descriptions_come_from_wherever_each_type_keeps_them(self, fake_mcp_server):
        # Dataset and MLModel carry a top-level name (MLModel also a top-level
        # description and no `properties`); Dashboard, Chart and DataJob only carry
        # properties.name. The DataJob's URN nests its flow's, so a naive URN split
        # would hand back the flow, not the job.
        assets = _run(discover_impact_via_mcp())
        by_name = {a.name: a for a in assets}
        assert by_name["syn.scorer_v1"].role == "Model trained on branch 1."
        assert by_name["syn.shared_view"].role == "Dashboard fed by branch 1, branch 2 and chart 4."
        assert by_name["syn.train_job"].role == "Job that trains the scorer from branch 1."
        assert by_name["syn.chart_4"].role == "Chart built from branch 4."

    def test_the_fixture_only_uses_lineage_edges_datahub_can_store(self):
        kind_of = {n: t for n, (t, _d) in fake_server.NODES.items()}
        kind_of[fake_server.ANCHOR_NAME] = "DATASET"
        to_entity = {"DATASET": "dataset", "DASHBOARD": "dashboard", "CHART": "chart",
                     "ML_MODEL": "mlModel", "DATA_JOB": "dataJob"}
        for up, downs in fake_server.EDGES.items():
            for down in downs:
                pair = (to_entity[kind_of[up]], to_entity[kind_of[down]])
                assert pair in graph.DATAHUB_LINEAGE_EDGES, (up, down, pair)

    def test_costing_and_write_back_work_on_the_mixed_closure(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        a = build_assessment("RCS-2026", assets)

        # The engine finds the model and the dashboards by their entity type; their
        # names (`syn.scorer_v1`, `syn.shared_view`) say nothing about it.
        act = next(s for s in a.scenarios if s.decision == "ACT_NOW")
        rebuild = next(e for e in act.cost_of_action if e.label.startswith("Model rebuild"))
        assert rebuild.value == se.ML_MODEL_REBUILD_COST
        recert = next(e for e in act.cost_of_action if e.label.startswith("Report re-cert"))
        assert recert.value == 2 * se.REPORT_RECERT_COST  # syn.shared_view + syn.exec_view

        # The write-back targets the URNs the server returned, one per asset, each
        # of the entity type the card says it is.
        payload = writeback_payload(a)
        assert payload["targets"] == [x.urn for x in a.affected_assets]
        assert len(set(payload["targets"])) == len(a.affected_assets)
        for asset in a.affected_assets:
            assert asset.urn.split(":")[2] == asset.entity_type
        by_urn = {x.urn: x for x in a.affected_assets}
        assert by_urn["urn:li:mlModel:(urn:li:dataPlatform:mlflow,syn.scorer_v1,PROD)"].entity_type == "mlModel"

    def test_convergence_keeps_a_single_asset_for_the_shared_child(self, fake_mcp_server):
        assets = _run(discover_impact_via_mcp())
        names = [a.name for a in assets]
        assert names.count("syn.shared_view") == 1

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
