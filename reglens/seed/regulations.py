"""The fictional regulation RegLens reasons about.

RCS-2026 is INVENTED, issued by an INVENTED supervisor, on purpose: it lets us
build a realistic implement/defer/minimum-compliance trade-off without making any
claim about real-world regulation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Regulation:
    id: str
    title: str
    issuer: str
    summary: str
    deadline_months: int
    # Free-text keywords the agent searches DataHub for, to *discover* impact
    # rather than being told it. The lineage in DataHub does the rest.
    seed_search_terms: tuple[str, ...]


RCS_2026 = Regulation(
    id="RCS-2026",
    title="Enhanced Customer Risk Classification Standard",
    issuer="European Banking Supervisory Council (fictional)",
    summary=(
        "Banks must recompute every customer's risk tier under an expanded feature "
        "set and a stricter classification methodology, and reflect the revised tiers "
        "in regulatory capital reporting. Non-compliance or misstated tiers within the "
        "compliance window carry escalating supervisory penalties."
    ),
    deadline_months=12,
    seed_search_terms=(
        "customer risk",
        "risk classification",
        "risk profile",
        "risk scoring",
        "capital reporting",
        "regulatory risk report",
    ),
)

# The registry the CLI selects from. Add more fictional regs here to demo breadth.
REGULATIONS = {RCS_2026.id: RCS_2026}
