"""A tiny, standalone fake DataHub MCP server, for testing a real MCP round
trip without Docker/DataHub/uvx.

Its lineage graph is deliberately NOT reglens/seed/graph.py's Northstar graph:
different node names, a fan-out (one node with five children), a six-hop-deep
chain, a convergence (three parents feeding one dashboard), and a genuine cycle
(syn.cycle_node_a <-> syn.cycle_node_b). A parser that can only get the right
answer by knowing Northstar's shape in advance has no way to get this graph
right by coincidence.

It is a MIXED-TYPE graph, and every entity carries the URN and the fields the
real tool returns for its type. Verified against acryldata/mcp-server-datahub:
`tools/lineage.py` runs the `GetEntityLineage` GraphQL query in
`gql/entity_details.gql`, whose `entityPreview` fragment selects, per type:

    Dataset    urn:li:dataset:(urn:li:dataPlatform:<p>,<name>,<env>)
               name, platform, properties{name,description}, subTypes
    Dashboard  urn:li:dashboard:(<tool>,<id>)
               tool, dashboardId, platform, properties{name,description}
    Chart      urn:li:chart:(<tool>,<id>)
               tool, chartId, properties{name,description}
    MLModel    urn:li:mlModel:(urn:li:dataPlatform:<p>,<name>,<env>)
               name, description, origin, platform     (NO `properties`)
    DataJob    urn:li:dataJob:(urn:li:dataFlow:(<orchestrator>,<flow>,<env>),<job>)
               jobId, dataFlow{urn,orchestrator,flowId,cluster,properties},
               properties{name,description}

and the tool wraps them as

    {"downstreams": {"searchResults": [
        {"entity": {"urn": ..., "type": "DATASET" | "DASHBOARD" | "ML_MODEL" |
                    "DATA_JOB" | "CHART", ...}, "degree": <int>},
        ...
    ], "offset": 0, "returned": N, "hasMore": False}}

The edges only use pairs DataHub can actually store (see
reglens.seed.graph.DATAHUB_LINEAGE_EDGES): a model is reached through the job
that trains it and left through the job that uses it, dashboards consume
datasets and charts, and there is no direct dataset -> model edge.

Two nodes are traps for a parser that trusts the wrong signal: a dataset whose
`subTypes` says "Dashboard" (still a dataset), and names that say nothing about
the entity type (`syn.scorer_v1` is a model, `syn.shared_view` is a dashboard).

It also exposes the two mutation tools RegLens's optional MCP write-back calls, with
the REAL signatures (acryldata/mcp-server-datahub commit 38e4523, quoted in full in
reglens/agent/mcp_client.py):

    update_description(entity_urn: str,
                       operation: Literal["replace", "append", "remove"] = "replace",
                       description: str | None = None, column_path: str | None = None)
        src/mcp_server_datahub/tools/descriptions.py
    add_terms(term_urns: list[str], entity_urns: list[str],
              column_paths: list[str | None] | None = None)
        the function is `add_glossary_terms` in src/mcp_server_datahub/tools/terms.py
        but mcp_server.py registers it under the name `add_terms`

Like the real server they are only registered when TOOLS_IS_MUTATION_ENABLED is true,
and `add_terms` rejects a term URN that does not exist. Every tool here rejects an
argument name it does not have; that is stricter than mcp's own arg validation, which
silently drops unknown names (checked on mcp 1.30 and 2.2), and matches what a
JSON-schema-validating FastMCP does. If FAKE_DATAHUB_RECORD names a file, every
accepted call is appended to it as one JSON line, so a test can see what the server
actually received. FAKE_DATAHUB_KNOWN_TERMS is a comma-separated list of the glossary
term URNs that exist.

Run directly as a subprocess over stdio; see tests/test_mcp_lineage_roundtrip.py.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
from typing import Literal

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _MCPServerImpl
    from mcp.server.fastmcp.exceptions import ToolError
except ImportError:  # mcp 2.x renamed FastMCP -> MCPServer
    from mcp.server.mcpserver import MCPServer as _MCPServerImpl
    from mcp.server.mcpserver.exceptions import ToolError

PLATFORM = "snowflake"
ENV = "PROD"
DASHBOARD_TOOL = "powerbi"
CHART_TOOL = "looker"
MODEL_PLATFORM = "mlflow"
ORCHESTRATOR = "airflow"

# Same URN shape as reglens.seed.graph.dataset_urn(), and the same anchor name
# reglens_agent.ANCHOR uses, so the round-trip test queries the exact anchor
# identity the real agent would — only what's *downstream* of it differs from
# the seeded Northstar graph.
ANCHOR_NAME = "risk.customer_risk_profile"
ANCHOR_URN = f"urn:li:dataset:(urn:li:dataPlatform:{PLATFORM},{ANCHOR_NAME},{ENV})"

# name -> (DataHub EntityType, description). None of these names appear
# anywhere in reglens/seed/graph.py.
NODES: dict[str, tuple[str, str]] = {
    "syn.branch_1": ("DATASET", "Fan-out branch 1."),
    "syn.branch_2": ("DATASET", "Fan-out branch 2."),
    "syn.branch_3": ("DATASET", "Fan-out branch 3."),
    "syn.branch_4": ("DATASET", "Fan-out branch 4."),
    "syn.branch_5": ("DATASET", "Fan-out branch 5."),
    "syn.train_job": ("DATA_JOB", "Job that trains the scorer from branch 1."),
    "syn.scorer_v1": ("ML_MODEL", "Model trained on branch 1."),
    "syn.scoring_job": ("DATA_JOB", "Job that runs the scorer."),
    "syn.scored_output": ("DATASET", "Dataset the scoring job writes."),
    "syn.exec_view": ("DASHBOARD", "Dashboard six hops downstream."),
    "syn.chart_4": ("CHART", "Chart built from branch 4."),
    "syn.shared_view": ("DASHBOARD", "Dashboard fed by branch 1, branch 2 and chart 4."),
    "syn.cycle_node_a": ("DATASET", "First half of a lineage cycle."),
    "syn.cycle_node_b": ("DATASET", "Second half of a lineage cycle."),
    "syn.leaf_4": ("DATASET", "Leaf fed only by branch 4."),
    "syn.leaf_5": ("DATASET", "Leaf fed only by branch 5."),
    "syn.tagged_dashboard": ("DATASET", "A dataset whose subtype tag says Dashboard."),
}

# upstream -> [downstream, ...], rooted at the anchor: fan-out, a six-hop chain
# through a training job, a model and a scoring job, a convergence, a cycle.
EDGES: dict[str, list[str]] = {
    ANCHOR_NAME: [
        "syn.branch_1", "syn.branch_2", "syn.branch_3", "syn.branch_4", "syn.branch_5",
    ],
    "syn.branch_1": ["syn.train_job", "syn.shared_view"],
    "syn.branch_2": ["syn.shared_view"],
    "syn.branch_3": ["syn.cycle_node_a"],
    "syn.branch_4": ["syn.leaf_4", "syn.chart_4"],
    "syn.branch_5": ["syn.leaf_5", "syn.tagged_dashboard"],
    "syn.chart_4": ["syn.shared_view"],
    "syn.train_job": ["syn.scorer_v1"],
    "syn.scorer_v1": ["syn.scoring_job"],
    "syn.scoring_job": ["syn.scored_output"],
    "syn.scored_output": ["syn.exec_view"],
    "syn.cycle_node_a": ["syn.cycle_node_b"],
    "syn.cycle_node_b": ["syn.cycle_node_a"],
}


def _urn(name: str) -> str:
    """The URN DataHub uses for this node, by its entity type."""
    etype = NODES[name][0] if name in NODES else "DATASET"
    if etype == "DASHBOARD":
        return f"urn:li:dashboard:({DASHBOARD_TOOL},{name})"
    if etype == "CHART":
        return f"urn:li:chart:({CHART_TOOL},{name})"
    if etype == "ML_MODEL":
        return f"urn:li:mlModel:(urn:li:dataPlatform:{MODEL_PLATFORM},{name},{ENV})"
    if etype == "DATA_JOB":
        return f"urn:li:dataJob:(urn:li:dataFlow:({ORCHESTRATOR},{name},{ENV}),{name})"
    return f"urn:li:dataset:(urn:li:dataPlatform:{PLATFORM},{name},{ENV})"


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


def _platform(name: str) -> dict:
    return {"urn": f"urn:li:dataPlatform:{name}", "name": name}


def _entity_dict(name: str) -> dict:
    """The `entity` object the real tool returns for this node's type."""
    etype, desc = NODES[name]
    urn = _urn(name)
    if etype == "DATASET":
        entity = {
            "urn": urn, "type": "DATASET", "name": name, "platform": _platform(PLATFORM),
            "properties": {"name": name, "description": desc},
            "subTypes": {"typeNames": ["Table"]},
        }
        if name == "syn.tagged_dashboard":
            entity["subTypes"] = {"typeNames": ["Dashboard"]}
        return entity
    if etype == "DASHBOARD":
        return {
            "urn": urn, "type": "DASHBOARD", "tool": DASHBOARD_TOOL, "dashboardId": name,
            "platform": _platform(DASHBOARD_TOOL),
            "properties": {"name": name, "description": desc},
        }
    if etype == "CHART":
        return {
            "urn": urn, "type": "CHART", "tool": CHART_TOOL, "chartId": name,
            "properties": {"name": name, "description": desc},
        }
    if etype == "ML_MODEL":
        # MLModel is selected with top-level name/description/origin and no `properties`.
        return {
            "urn": urn, "type": "ML_MODEL", "name": name, "description": desc,
            "origin": ENV, "platform": _platform(MODEL_PLATFORM),
        }
    if etype == "DATA_JOB":
        return {
            "urn": urn, "type": "DATA_JOB", "jobId": name,
            "dataFlow": {
                "urn": f"urn:li:dataFlow:({ORCHESTRATOR},{name},{ENV})",
                "orchestrator": ORCHESTRATOR, "flowId": name, "cluster": ENV,
                "properties": {"name": name},
            },
            "properties": {"name": name, "description": desc},
        }
    raise ValueError(etype)


# name -> the real signature, so unknown argument names can be rejected.
_SIGNATURES: dict[str, inspect.Signature] = {}


class _StrictServer(_MCPServerImpl):
    """Rejects any argument name the tool's signature does not have."""

    async def call_tool(self, name, arguments, *args, **kwargs):
        sig = _SIGNATURES.get(name)
        if sig is not None:
            unknown = sorted(set(arguments or {}) - set(sig.parameters))
            if unknown:
                raise ValueError(
                    f"Unexpected keyword argument(s) for tool '{name}': {unknown}. "
                    f"It takes: {list(sig.parameters)}"
                )
        return await super().call_tool(name, arguments, *args, **kwargs)


srv = _StrictServer("fake-datahub-lineage-test")


def _tool(name: str):
    def register(fn):
        _SIGNATURES[name] = inspect.signature(fn)
        return srv.tool(name=name)(fn)

    return register


def _record(tool: str, **arguments) -> None:
    path = os.environ.get("FAKE_DATAHUB_RECORD")
    if path:
        with open(path, "a") as f:
            f.write(json.dumps({"tool": tool, "arguments": arguments}) + "\n")


def _truthy(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() in {"1", "true", "yes"}


@_tool("search")
def search(query: str) -> dict:
    return {"searchResults": []}


@_tool("get_lineage")
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


if _truthy("TOOLS_IS_MUTATION_ENABLED"):

    @_tool("update_description")
    def update_description(
        entity_urn: str,
        operation: Literal["replace", "append", "remove"] = "replace",
        description: str | None = None,
        column_path: str | None = None,
    ) -> dict:
        if not entity_urn:
            raise ToolError("entity_urn cannot be empty")
        if operation in ("replace", "append") and not description:
            raise ToolError(f"description is required for '{operation}' operation")
        _record(
            "update_description", entity_urn=entity_urn, operation=operation,
            description=description, column_path=column_path,
        )
        verb = "updated" if operation in ("replace", "append") else "removed"
        return {
            "success": True, "urn": entity_urn, "column_path": column_path,
            "message": f"Description {verb} successfully",
        }

    @_tool("add_terms")
    def add_terms(
        term_urns: list[str],
        entity_urns: list[str],
        column_paths: list[str | None] | None = None,
    ) -> dict:
        if not term_urns:
            raise ToolError("term_urns cannot be empty")
        if not entity_urns:
            raise ToolError("entity_urns cannot be empty")
        known = {t for t in os.environ.get("FAKE_DATAHUB_KNOWN_TERMS", "").split(",") if t}
        missing = [t for t in term_urns if t not in known]
        if missing:
            raise ToolError(
                f"The following glossary term URNs do not exist in DataHub: {', '.join(missing)}. "
                "Please use the search tool with entity_type filter to find existing glossary "
                "terms, or create the terms first before assigning them."
            )
        if column_paths is not None and len(column_paths) != len(entity_urns):
            raise ToolError(
                f"column_paths length ({len(column_paths)}) must match "
                f"entity_urns length ({len(entity_urns)})"
            )
        _record("add_terms", term_urns=term_urns, entity_urns=entity_urns, column_paths=column_paths)
        return {
            "success": True,
            "message": f"Successfully added {len(term_urns)} glossary term(s) "
                       f"to {len(entity_urns)} entit(ies)",
        }


if __name__ == "__main__":
    asyncio.run(srv.run_stdio_async())
