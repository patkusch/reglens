"""Seed the fictional "Northstar Bank" into a local DataHub.

Run AFTER `datahub docker quickstart` is up and you've set DATAHUB_GMS_URL /
DATAHUB_TOKEN (see .env.template):

    python -m reglens.seed.seed_northstar

The asset list + lineage live in reglens/seed/graph.py (dependency-free, shared
with the agent's deterministic fallback). This file is only the DataHub write.

GUARANTEED CORE: datasets + owners + the dataset lineage chain. Always renders and
always supports the write-back demo.
OPTIONAL UPGRADE (TODO): promote reports -> Dashboard entities and the model ->
a real MLModel entity. Not needed to ship.
"""
from __future__ import annotations

import sys

from datahub.sdk import CorpUserUrn, DataHubClient, Dataset, DatasetUrn

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


def main() -> int:
    client = _client()
    print(f"Seeding Northstar Bank into {DATAHUB_GMS_URL} on platform '{PLATFORM}'...")

    for name, subtype, desc, schema, owner in ASSETS:
        ds = Dataset(platform=PLATFORM, name=name, description=desc, schema=schema)
        try:
            ds.add_owner(CorpUserUrn(owner))
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] owner on {name}: {e}")
        try:
            ds.set_subtype(subtype)
        except Exception:
            pass
        client.entities.upsert(ds)
        print(f"  + {subtype:<10} {name}")

    for up, down in LINEAGE:
        try:
            client.lineage.add_lineage(upstream=urn(up), downstream=urn(down))
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
