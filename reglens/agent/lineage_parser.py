"""Parses the DataHub MCP server's *actual* `get_lineage` response shape.

This is deliberately independent of `reglens/seed/graph.py`. Every URN, name,
entity type and hop count used here comes from the dict the MCP server handed
back — never from RegLens' own seeded lineage edges. That is what makes this a
real parse of "whatever DataHub says" rather than a lookup into "the graph we
already know we seeded".

The shape parsed is the one `acryldata/mcp-server-datahub`'s `get_lineage` tool
actually returns (see its `tools/lineage.py` and the `GetEntityLineage` GraphQL
query it runs), after MCP JSON-decoding::

    {
      "downstreams": {                 # or "upstreams", depending on direction
        "searchResults": [
          {
            "entity": {
              "urn": "urn:li:...",
              "type": "DATASET" | "DASHBOARD" | "ML_MODEL" | "DATA_FLOW" | ...,
              "name": "...",            # present for Dataset entities only
              "properties": {"name": "...", "description": "..."},  # others
            },
            "degree": 1,                # hop count; DataHub buckets far hops as "3+"
          },
          ...
        ],
        "offset": 0, "returned": N, "hasMore": false,
      }
    }

The anchor entity itself is never part of its own downstream/upstream results,
so callers pass its URN/name in separately to prepend it to the returned list.
"""
from __future__ import annotations

from typing import Any

from reglens.models import AffectedAsset

# DataHub GraphQL `EntityType` enum values -> the lowerCamelCase strings RegLens
# uses elsewhere (models.AffectedAsset.entity_type, seed/graph.SUBTYPE_TO_ENTITY).
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


def _entity_type(raw_type: Any) -> str:
    """DataHub's EntityType enum value -> RegLens' entity_type string.

    Unknown/missing types fall back to "dataset" (the safest default: that's
    what every affected asset was before this parser existed) rather than
    raising, so a DataHub entity kind RegLens hasn't seen yet doesn't crash the
    demo — it just shows up un-fancily typed.
    """
    if not isinstance(raw_type, str) or not raw_type:
        return "dataset"
    if raw_type in _ENTITY_TYPE_MAP:
        return _ENTITY_TYPE_MAP[raw_type]
    parts = raw_type.lower().split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _entity_name(entity: dict) -> str:
    """Best-effort short name, independent of which DataHub entity kind this is.

    Dataset entities carry a top-level `name`; every other entity kind (
    Dashboard, MLModel, DataFlow, ...) only carries `properties.name`. Falling
    back to decoding the URN itself covers whatever's left.
    """
    if entity.get("name"):
        return entity["name"]
    props = entity.get("properties") or {}
    if props.get("name"):
        return props["name"]
    urn = entity.get("urn") or ""
    inner = urn.split("(", 1)[-1].rstrip(")")
    fields = [f for f in inner.split(",") if f]
    if len(fields) >= 2:
        return fields[1]
    return fields[0] if fields else urn


def _entity_role(entity: dict) -> str:
    props = entity.get("properties") or {}
    if props.get("description"):
        return props["description"]
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
            entity_type=_entity_type(entity.get("type")),
            role=_entity_role(entity),
        )
        scored.append((_degree_sort_key(item.get("degree")), urn, asset))

    scored.sort(key=lambda t: (t[0], t[1]))
    anchor_asset = AffectedAsset(
        urn=anchor_urn, name=anchor_name, entity_type="dataset", role=anchor_role
    )
    return [anchor_asset] + [a for _, _, a in scored]
