"""Parses the DataHub MCP server's *actual* `get_lineage` response shape.

This is deliberately independent of `reglens/seed/graph.py`. Every URN, name,
entity type and hop count used here comes from the dict the MCP server handed
back — never from RegLens' own seeded lineage edges. That is what makes this a
real parse of "whatever DataHub says" rather than a lookup into "the graph we
already know we seeded".

The shape parsed is the one `acryldata/mcp-server-datahub`'s `get_lineage` tool
actually returns (see its `tools/lineage.py`, which runs the `GetEntityLineage`
GraphQL query from `gql/entity_details.gql`), after MCP JSON-decoding::

    {
      "downstreams": {                 # or "upstreams", depending on direction
        "searchResults": [
          {
            "entity": {"urn": "urn:li:...", "type": "DATASET" | ..., ...},
            "degree": 1,                # hop count
          },
          ...
        ],
        "offset": 0, "returned": N, "hasMore": false,
      }
    }

What is inside `entity` depends on the entity type (that query's `entityPreview`
fragment). These are the fields that matter here::

    Dataset    name, properties{name, description}, editableProperties{...}
    Dashboard  tool, dashboardId, properties{name, description}
    MLModel    name, description, origin            (no `properties` at all)
    DataJob    jobId, dataFlow{...}, properties{name, description}
    Chart      tool, chartId, properties{name, description}

So the name and the description each live in a different place per type, and this
parser looks in all of them.

The node kind comes from the entity's URN (`urn:li:dashboard:(...)`,
`urn:li:mlModel:(...)`, `urn:li:dataJob:(...)`, ...), which is DataHub's own
identity for the entity, never from a subtype tag or from anything RegLens
seeded. The GraphQL `type` enum is only a fallback for a URN that can't be read.

The anchor entity itself is never part of its own downstream/upstream results,
so callers pass its URN/name in separately to prepend it to the returned list.
"""
from __future__ import annotations

from typing import Any

from reglens.models import AffectedAsset

# DataHub GraphQL `EntityType` enum values -> DataHub URN entity types (the same
# lowerCamelCase strings `models.AffectedAsset.entity_type` uses). Only a
# fallback: the URN itself is the first choice.
_ENTITY_TYPE_MAP = {
    "DATASET": "dataset",
    "DASHBOARD": "dashboard",
    "CHART": "chart",
    "DATA_FLOW": "dataFlow",
    "DATA_JOB": "dataJob",
    "ML_MODEL": "mlModel",
    "ML_MODEL_GROUP": "mlModelGroup",
    "ML_FEATURE_TABLE": "mlFeatureTable",
    "ML_FEATURE": "mlFeature",
    "ML_PRIMARY_KEY": "mlPrimaryKey",
    "CONTAINER": "container",
}


def _split_urn(urn: str) -> tuple[str, list[str]] | None:
    """`urn:li:<type>:(<a>,<b>,...)` -> (type, [a, b, ...]), or None if unreadable.

    Fields are split on the commas that are not inside a nested URN, so a
    dataJob's `(urn:li:dataFlow:(airflow,flow,PROD),job)` gives two fields, not
    four. A URN with a single unparenthesised id (`urn:li:glossaryTerm:PII`)
    gives one field.
    """
    parts = urn.split(":", 3) if isinstance(urn, str) else []
    if len(parts) != 4 or parts[0] != "urn" or parts[1] != "li" or not parts[2] or not parts[3]:
        return None
    body = parts[3]
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    fields: list[str] = []
    depth = 0
    current = ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            fields.append(current)
            current = ""
        else:
            current += ch
    fields.append(current)
    return parts[2], fields


def _entity_type(urn: Any, raw_type: Any) -> str:
    """The entity's kind: its URN's entity type, else DataHub's `type` enum.

    Unknown/missing everywhere falls back to "dataset" rather than raising, so an
    entity kind RegLens hasn't seen yet doesn't crash the demo — it just shows up
    un-fancily typed.
    """
    split = _split_urn(urn)
    if split:
        return split[0]
    if isinstance(raw_type, str) and raw_type:
        if raw_type in _ENTITY_TYPE_MAP:
            return _ENTITY_TYPE_MAP[raw_type]
        parts = raw_type.lower().split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:])
    return "dataset"


def _entity_name(entity: dict) -> str:
    """Best-effort short name, whichever way this entity kind reports it.

    Dataset and MLModel carry a top-level `name`; Dashboard, Chart, DataJob and
    DataFlow only carry `properties.name`. Decoding the URN covers whatever's
    left: the second field of a URN is the entity's own id for every type here
    (dataset, mlModel, dashboard, chart, dataJob, dataFlow).
    """
    if entity.get("name"):
        return entity["name"]
    props = entity.get("properties") or {}
    if props.get("name"):
        return props["name"]
    urn = entity.get("urn") or ""
    split = _split_urn(urn)
    if not split:
        return urn
    fields = [f for f in split[1] if f]
    if len(fields) >= 2:
        return fields[1]
    return fields[0] if fields else urn


def _entity_role(entity: dict) -> str:
    """Description, wherever it lives: `properties` (Dataset, Dashboard, Chart,
    DataJob), top level (MLModel), or the human-edited `editableProperties`."""
    props = entity.get("properties") or {}
    if props.get("description"):
        return props["description"]
    if entity.get("description"):
        return entity["description"]
    editable = entity.get("editableProperties") or {}
    return editable.get("description", "")


def _degree_sort_key(degree: Any) -> tuple:
    """DataHub can report `degree` as an int, or as the string "3+" once a
    result is far enough away to fall into the last aggregation bucket. Sort
    real integers first (by value), then bucketed/unknown values last.
    """
    if isinstance(degree, bool):
        return (1, 0)
    if isinstance(degree, int):
        return (0, degree)
    if isinstance(degree, str):
        digits = "".join(ch for ch in degree if ch.isdigit())
        if digits:
            return (0, int(digits))
    return (1, 0)


def parse_lineage_assets(
    lineage_response: dict,
    *,
    anchor_urn: str,
    anchor_name: str,
    anchor_role: str = "",
    direction: str = "DOWNSTREAM",
) -> list[AffectedAsset]:
    """Walk a decoded `get_lineage` response into `AffectedAsset`s.

    `lineage_response` must already be a plain dict (see
    `DataHubMCP.decode_result`), i.e. the real MCP tool payload — not anything
    RegLens seeded. Raises `ValueError` if the response doesn't look like a
    `get_lineage` result at all (missing the expected top-level key), so a
    genuinely malformed/unexpected response is surfaced rather than silently
    treated as "no impact".
    """
    key = "upstreams" if direction.upper() == "UPSTREAM" else "downstreams"
    if key not in lineage_response:
        raise ValueError(
            f"Lineage response has no '{key}' key — got: {sorted(lineage_response)}"
        )
    direction_result = lineage_response.get(key) or {}
    results = direction_result.get("searchResults") or []

    seen: set[str] = {anchor_urn}
    scored: list[tuple[tuple, str, AffectedAsset]] = []
    for item in results:
        entity = item.get("entity") or {}
        urn = entity.get("urn")
        if not urn or urn in seen:
            continue
        seen.add(urn)
        name = _entity_name(entity)
        asset = AffectedAsset(
            urn=urn,
            name=name,
            entity_type=_entity_type(urn, entity.get("type")),
            role=_entity_role(entity),
        )
        scored.append((_degree_sort_key(item.get("degree")), urn, asset))

    scored.sort(key=lambda t: (t[0], t[1]))
    anchor_asset = AffectedAsset(
        urn=anchor_urn,
        name=anchor_name,
        entity_type=_entity_type(anchor_urn, None),
        role=anchor_role,
    )
    return [anchor_asset] + [a for _, _, a in scored]
