"""SDK write-back path: the one the agent uses.

The requirement to *use* the MCP server is satisfied by the READ path. The
write-back goes through the DataHub SDK because it needs nothing but a token and a
GMS URL, and it does not depend on the MCP server's mutation tools being switched
on. `DataHubMCP.update_description` / `add_glossary_terms` in agent/mcp_client.py
can do the same over MCP, but they are an optional, unwired path, tested only
against a fake MCP server; the agent never calls them. One difference to know
about: the MCP `add_terms` tool rejects a glossary term that does not exist in
DataHub yet, whereas this path just references the term's URN.

Each target is written as the entity type its URN says it is: the SDK reads the
URN's entity type (`urn:li:dashboard:...`, `urn:li:mlModel:...`,
`urn:li:dataJob:...`, `urn:li:dataset:...`) and hands back a Dashboard, MLModel,
DataJob or Dataset, so the description and glossary term land on that entity's own
aspects (DashboardInfo, MLModelProperties, DataJobInfo, ...) rather than on a
dataset stand-in.
"""
from __future__ import annotations

from reglens.config import DATAHUB_GMS_URL, DATAHUB_TOKEN


def write_assessment_via_sdk(payload: dict, client=None) -> list[str]:
    """Attach the RegLens glossary term + description to each affected asset.

    `client` is a `DataHubClient`; by default one is built from the environment.
    Returns the list of URNs successfully updated.
    """
    if client is None:
        from datahub.sdk import DataHubClient  # local import; keep module import cheap

        client = DataHubClient(server=DATAHUB_GMS_URL, token=DATAHUB_TOKEN or "")
    updated: list[str] = []
    term = payload["glossary_term"]
    description = payload["description"]

    for urn in payload["targets"]:
        try:
            entity = client.entities.get(urn)
            kind = entity.urn.entity_type
            # Description (documentation) — inherited by the next person/agent.
            try:
                entity.set_description(description)
            except Exception:
                # Some entity types expose set_editable_description instead.
                try:
                    entity.set_editable_description(description)
                except Exception as e:  # noqa: BLE001
                    print(f"  [warn] description on {kind} {urn}: {e}")
            # Glossary term — queryable decision tag. Best-effort across versions.
            try:
                from datahub.metadata.urns import GlossaryTermUrn
                entity.add_term(GlossaryTermUrn(term))
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] glossary term on {kind} {urn}: {e}")
            client.entities.update(entity)
            updated.append(urn)
            print(f"  wrote assessment -> {kind:<9} {urn}")
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] could not update {urn}: {e}")
    return updated
