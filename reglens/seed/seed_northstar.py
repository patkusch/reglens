"""Seed the fictional "Northstar Bank" into a local DataHub.

Run AFTER `datahub docker quickstart` is up and you've set DATAHUB_GMS_URL /
DATAHUB_TOKEN (see .env.template):

    python -m reglens.seed.seed_northstar

The asset list + lineage live in reglens/seed/graph.py (dependency-free, shared
with the agent's deterministic fallback). This file is only the DataHub write.

Every asset is written as the DataHub entity it really is, and every lineage edge
is stored the way DataHub stores it for that pair of entity types:

    Table      -> Dataset    schema + owner; dataset->dataset via UpstreamLineage
    Dashboard  -> Dashboard  DashboardInfo.datasetEdges holds the datasets it reads
    ML Model   -> MLModel    MLModelProperties.trainingJobs / .downstreamJobs hold
                             the jobs that train it and use it
    Pipeline   -> DataFlow + DataJob   DataJobInputOutput holds the datasets the
                             job reads and writes

`build_plan()` builds all of that in memory with no server, so the tests can check
the exact entities and aspects that would be sent; `main()` sends them.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

from datahub.sdk import (
    CorpUserUrn,
    Dashboard,
    DataFlow,
    DataHubClient,
    DataJob,
    Dataset,
    DatasetUrn,
    MLModel,
)

from reglens.config import BANK_PLATFORM, DATAHUB_GMS_URL, DATAHUB_TOKEN
from reglens.seed import graph

# Keep the platform consistent between seed + agent.
graph.PLATFORM = BANK_PLATFORM
PLATFORM = BANK_PLATFORM

# Re-export for the agent (backwards-compatible imports).
ASSETS = graph.ASSETS
LINEAGE = graph.LINEAGE


def urn(name: str) -> DatasetUrn:
    return DatasetUrn(platform=PLATFORM, name=name)


def _client() -> DataHubClient:
    return DataHubClient(server=DATAHUB_GMS_URL, token=DATAHUB_TOKEN or "")


@dataclass
class SeedPlan:
    """Everything `main()` sends: entities to upsert, and the dataset->dataset
    edges that are sent as lineage calls (every other edge lives inside an entity)."""
    entities: list = field(default_factory=list)
    dataset_edges: list[tuple[str, str]] = field(default_factory=list)


def build_plan() -> SeedPlan:
    """Build the whole Northstar graph as real DataHub entities, without a server."""
    meta = {name: (kind, desc, schema, owner) for name, kind, desc, schema, owner in ASSETS}
    upstreams: dict[str, list[str]] = {}
    downstreams: dict[str, list[str]] = {}
    for up, down in LINEAGE:
        upstreams.setdefault(down, []).append(up)
        downstreams.setdefault(up, []).append(down)

    def entity_type(name: str) -> str:
        return graph.entity_type_of(name)

    def urns_of(names: list[str], *types: str) -> list[str]:
        return [graph.urn_for(n) for n in names if entity_type(n) in types]

    plan = SeedPlan()
    for name, (kind, desc, schema, owner) in meta.items():
        etype = graph.KIND_TO_ENTITY[kind]
        for other in upstreams.get(name, []):
            if (entity_type(other), etype) not in graph.DATAHUB_LINEAGE_EDGES:
                raise ValueError(f"DataHub cannot store lineage {other} -> {name}")

        if etype == "dataset":
            entity = Dataset(platform=PLATFORM, name=name, description=desc, schema=schema)
            entity.set_subtype(kind)
            plan.dataset_edges += [
                (graph.dataset_urn(up), graph.dataset_urn(name))
                for up in upstreams.get(name, [])
                if entity_type(up) == "dataset"
            ]
            plan.entities.append(entity)
        elif etype == "dashboard":
            entity = Dashboard(
                name=name,
                platform=graph.DASHBOARD_TOOL,
                description=desc,
                input_datasets=urns_of(upstreams.get(name, []), "dataset"),
            )
            plan.entities.append(entity)
        elif etype == "mlModel":
            entity = MLModel(
                id=name,
                platform=graph.MODEL_PLATFORM,
                env=graph.ENV,
                name=name,
                description=desc,
                training_jobs=urns_of(upstreams.get(name, []), "dataJob"),
                downstream_jobs=urns_of(downstreams.get(name, []), "dataJob"),
            )
            plan.entities.append(entity)
        elif etype == "dataJob":
            flow = DataFlow(
                name=name, platform=graph.ORCHESTRATOR, env=graph.ENV, description=desc
            )
            flow.add_owner(CorpUserUrn(owner))
            entity = DataJob(
                name=name,
                flow=flow,
                description=desc,
                inlets=urns_of(upstreams.get(name, []), "dataset"),
                outlets=urns_of(downstreams.get(name, []), "dataset"),
            )
            plan.entities.append(flow)
            plan.entities.append(entity)
        else:  # pragma: no cover - KIND_TO_ENTITY only maps the four above
            raise ValueError(f"No seed rule for {kind}")
        entity.add_owner(CorpUserUrn(owner))
    return plan


def main() -> int:
    client = _client()
    print(f"Seeding Northstar Bank into {DATAHUB_GMS_URL} on platform '{PLATFORM}'...")
    plan = build_plan()

    for entity in plan.entities:
        client.entities.upsert(entity)
        print(f"  + {entity.urn.entity_type:<10} {entity.urn}")

    for up, down in plan.dataset_edges:
        try:
            client.lineage.add_lineage(upstream=up, downstream=down)
            print(f"  ~ {up}  ->  {down}")
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] lineage {up}->{down}: {e}")

    print(
        "\nDone. Open http://localhost:9002, search 'customer_risk_profile', and "
        "view its downstream lineage to see the RCS-2026 blast radius."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
