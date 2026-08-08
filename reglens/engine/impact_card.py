"""Render the Impact & Decision Card, and build the write-back payload.

The write-back is deliberately small and MCP-native: a glossary term plus a rich
description string, attached to each affected asset. That is exactly what the
DataHub MCP mutation tools support, and it shows up in the DataHub UI on camera.
"""
from __future__ import annotations

import json

from reglens.models import Assessment, Scenario


def _fmt(v: float) -> str:
    return f"£{v:,.0f}"


def _scenario_block(s: Scenario) -> str:
    lines = [f"  {s.decision}  (expected total {_fmt(s.expected_total_cost)})"]
    lines.append(f"    action {_fmt(s.action_total)} | inaction {_fmt(s.inaction_total)} | opportunity {_fmt(s.opportunity_total)}")
    lines.append(f"    duration {s.duration_months}m | capacity {s.change_capacity_fte_years} FTE-yrs | displaces: {s.displaced_initiative}")
    return "\n".join(lines)


def render_text(a: Assessment) -> str:
    out = []
    out.append("=" * 68)
    out.append(f" REGULATORY CHANGE: {a.regulation_title}  [{a.regulation_id}]")
    out.append("=" * 68)
    out.append(f" Impact: {a.impact}    Deadline: {a.deadline_months} months    "
               f"Assessed: {a.assessment_date}")
    types = {}
    for asset in a.affected_assets:
        types[asset.entity_type] = types.get(asset.entity_type, 0) + 1
    type_str = " / ".join(f"{v} {k}" for k, v in sorted(types.items()))
    out.append(f" Affected assets: {len(a.affected_assets)}  ({type_str})")
    out.append("-" * 68)
    out.append(" SCENARIOS")
    for s in a.scenarios:
        out.append(_scenario_block(s))
    out.append("-" * 68)
    out.append(f" RECOMMENDATION:  {a.recommendation}")
    out.append(f" Confidence:      {a.confidence}")
    out.append(f" Rationale:       {a.rationale}")
    out.append("=" * 68)
    out.append(" Every figure carries an assumption + confidence — challenge them.")
    return "\n".join(out)


def render_markdown(a: Assessment) -> str:
    """Markdown card for the repo / examples folder."""
    lines = [f"# Impact & Decision Card — {a.regulation_id}", ""]
    lines.append(f"**{a.regulation_title}**")
    lines.append("")
    lines.append(f"- **Impact:** {a.impact}")
    lines.append(f"- **Deadline:** {a.deadline_months} months")
    lines.append(f"- **Assessed:** {a.assessment_date}")
    lines.append(f"- **Affected assets:** {len(a.affected_assets)}")
    lines.append("")
    lines.append("| Decision | Action | Inaction | Opportunity | Expected total |")
    lines.append("|---|--:|--:|--:|--:|")
    for s in a.scenarios:
        lines.append(f"| {s.decision} | {_fmt(s.action_total)} | {_fmt(s.inaction_total)} "
                     f"| {_fmt(s.opportunity_total)} | **{_fmt(s.expected_total_cost)}** |")
    lines.append("")
    lines.append(f"## Recommendation: {a.recommendation}  (confidence {a.confidence})")
    lines.append("")
    lines.append(a.rationale)
    lines.append("")
    lines.append("### Affected assets")
    for asset in a.affected_assets:
        lines.append(f"- `{asset.name}` ({asset.entity_type}) — {asset.role}")
    return "\n".join(lines)


def writeback_payload(a: Assessment) -> dict:
    """What the agent attaches to EACH affected asset via MCP mutation tools.

    - glossary_term: a short, queryable tag of the decision + impact
    - description:   the human-readable assessment, so the next person inherits it
    """
    glossary_term = f"RegLens.{a.regulation_id}.{a.recommendation}"
    description = (
        f"[RegLens assessment {a.assessment_date}] {a.regulation_id} "
        f"({a.regulation_title}). Impact: {a.impact}. Decision: {a.recommendation} "
        f"(confidence {a.confidence}). {a.rationale}"
    )
    return {
        "glossary_term": glossary_term,
        "description": description,
        "targets": [asset.urn for asset in a.affected_assets],
    }


def to_json(a: Assessment) -> str:
    return json.dumps(a.as_dict(), indent=2, default=str)
