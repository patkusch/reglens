"""A tiny, standalone fake DataHub MCP server, for testing a real MCP round
trip without Docker/DataHub/uvx.

Its lineage graph is deliberately NOT reglens/seed/graph.py's Northstar graph:
different node names, a fan-out (one node with five children), a four-hop-deep
chain, a convergence (two parents feeding one child), and a genuine cycle
(cycle.node_a <-> cycle.node_b). A parser that can only get the right answer by
knowing Northstar's shape in advance has no way to get this graph right by
coincidence.

Speaks the exact response shape acryldata/mcp-server-datahub's `get_lineage`
tool returns for a downstream query (verified against its `tools/lineage.py`
and `GetEntityLineage` GraphQL query):

    {"downstreams": {"searchResults": [
        {"entity": {"urn": ..., "type": ..., "name"?: ..., "properties"?: {...}},
         "degree": <int, or "3+" once DataHub buckets far hops>},
        ...
    ], "offset": 0, "returned": N, "hasMore": False}}

Only Dataset entities get a top-level "name" (matching DataHub's GraphQL
`entityPreview` fragment, where `Dataset.name` is a direct field but Dashboard/
MLModel/DataFlow/Chart only expose `properties.name`) — so a parser that only
ever reads the top-level "name" would silently mis-name most of this graph.

Run directly as a subprocess over stdio; see tests/test_mcp_lineage_roundtrip.py.
"""
from __future__ import annotations

import asyncio

from mcp.server.mcpserver import MCPServer

PLATFORM = "snowflake"
ENV = "PROD"

# Same URN shape as reglens.seed.graph.dataset_urn(), and the same anchor name
# reglens_agent.ANCHOR uses, so the round-trip test queries the exact anchor
# identity the real agent would — only what's *downstream* of it differs from
# the seeded Northstar graph.
ANCHOR_NAME = "risk.customer_risk_profile"
ANCHOR_URN = f"urn:li:dataset:(urn:li:dataPlatform:{PLATFORM},{ANCHOR_NAME},{ENV})"


def _urn(name: str) -> str:
    return f"urn:li:dataset:(urn:li:dataPlatform:{PLATFORM},{name},{ENV})"


# name -> (DataHub EntityType, description). None of these names appear
# anywhere in reglens/seed/graph.py.
NODES: dict[str, tuple[str, str]] = {
    "syn.branch_1": ("DATASET", "Fan-out branch 1."),
    "syn.branch_2": ("DATASET", "Fan-out branch 2."),
    "syn.branch_3": ("DATASET", "Fan-out branch 3."),
    "syn.branch_4": ("DATASET", "Fan-out branch 4."),
    "syn.branch_5": ("DATASET", "Fan-out branch 5."),
    "syn.model_from_branch_1": ("ML_MODEL", "Model scored from branch 1."),
    "syn.shared_report": ("DASHBOARD", "Dashboard fed by both branch 1 and branch 2."),
    "syn.deep_pipeline": ("DATA_FLOW", "Pipeline three hops downstream."),
    "syn.deepest_chart": ("CHART", "Chart four hops downstream."),
    "syn.cycle_node_a": ("DATASET", "First half of a lineage cycle."),
    "syn.cycle_node_b": ("DATASET", "Second half of a lineage cycle."),
    "syn.leaf_4": ("DATASET", "Leaf fed only by branch 4."),
    "syn.leaf_5": ("DATASET", "Leaf fed only by branch 5."),
}

# upstream -> [downstream, ...], rooted at the anchor. Fan-out, depth-4 chain,
# a convergence, and a genuine cycle.
EDGES: dict[str, list[str]] = {
    ANCHOR_NAME: [
        "syn.branch_1", "syn.branch_2", "syn.branch_3", "syn.branch_4", "syn.branch_5",
    ],
    "syn.branch_1": ["syn.model_from_branch_1", "syn.shared_report"],
    "syn.branch_2": ["syn.shared_report"],
    "syn.branch_3": ["syn.cycle_node_a"],
    "syn.branch_4": ["syn.leaf_4"],
    "syn.branch_5": ["syn.leaf_5"],
    "syn.shared_report": ["syn.deep_pipeline"],
    "syn.deep_pipeline": ["syn.deepest_chart"],
    "syn.cycle_node_a": ["syn.cycle_node_b"],
    "syn.cycle_node_b": ["syn.cycle_node_a"],
}


def _downstream_closure(anchor: str) -> list[tuple[str, int]]:
    """BFS with a visited set — the same trick a real index-backed lineage
    search uses to terminate cleanly on a cyclic graph."""
    degree = {anchor: 0}
    order: list[str] = []
    queue = [anchor]
    while queue:
        node = queue.pop(0)
        for child in EDGES.get(node, []):
            if child not in degree:
                degree[child] = degree[node] + 1
                order.append(child)
                queue.append(child)
    return [(n, degree[n]) for n in order]


def _entity_dict(name: str) -> dict:
    etype, desc = NODES[name]
    entity: dict = {"urn": _urn(name), "type": etype}
    if etype == "DATASET":
        # Dataset entities carry a top-level `name` per DataHub's GraphQL
        # entityPreview fragment.
        entity["name"] = name
    entity["properties"] = {"name": name, "description": desc}
    return entity


srv = MCPServer("fake-datahub-lineage-test")


@srv.tool()
def search(query: str) -> dict:
    return {"searchResults": []}


@srv.tool()
def get_lineage(
    urn: str,
    upstream: bool = True,
    max_hops: int = 1,
    max_results: int = 30,
    column: str | None = None,
    query: str | None = None,
    filter: str | None = None,
    offset: int = 0,
) -> dict:
    if upstream or urn != ANCHOR_URN:
        return {"upstreams": {"searchResults": [], "offset": 0, "returned": 0, "hasMore": False}}

    results = [
        {"entity": _entity_dict(name), "degree": degree}
        for name, degree in _downstream_closure(ANCHOR_NAME)
    ]
    results = results[offset : offset + max_results]
    return {
        "downstreams": {
            "searchResults": results,
            "offset": offset,
            "returned": len(results),
            "hasMore": False,
        }
    }


if __name__ == "__main__":
    asyncio.run(srv.run_stdio_async())
