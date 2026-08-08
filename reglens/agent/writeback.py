"""Reliable SDK write-back path (fallback / alternative to the MCP mutation tools).

The requirement to *use* the MCP server is satisfied by the READ path. The
write-back can go through MCP mutation tools (preferred, one integration) or the
SDK (rock-solid). This module is the SDK path, so your demo's "agent writes the
decision back into DataHub" always works even if MCP mutation tool names drift.
"""
from __future__ import annotations

from reglens.config import DATAHUB_GMS_URL, DATAHUB_TOKEN


def write_assessment_via_sdk(payload: dict) -> list[str]:
    """Attach the RegLens glossary term + description to each affected asset.

    Returns the list of URNs successfully updated.
    """
    from datahub.sdk import DataHubClient  # local import; keep module import cheap

    client = DataHubClient(server=DATAHUB_GMS_URL, token=DATAHUB_TOKEN or "")
    updated: list[str] = []
    term = payload["glossary_term"]
    description = payload["description"]

    for urn in payload["targets"]:
        try:
            entity = client.entities.get(urn)
            # Description (documentation) — inherited by the next person/agent.
            try:
                entity.set_description(description)
            except Exception:
                # Some entity types expose set_editable_description instead.
                try:
                    entity.set_editable_description(description)
                except Exception as e:  # noqa: BLE001
                    print(f"  [warn] description on {urn}: {e}")
            # Glossary term — queryable decision tag. Best-effort across versions.
            try:
                from datahub.metadata.urns import GlossaryTermUrn
                entity.add_term(GlossaryTermUrn(term))
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] glossary term on {urn}: {e}")
            client.entities.update(entity)
            updated.append(urn)
            print(f"  wrote assessment -> {urn}")
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] could not update {urn}: {e}")
    return updated
