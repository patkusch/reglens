"""Plain dataclasses shared across the seed, engine, and agent.

Everything the scenario engine produces is transparent: every number carries an
assumption string and a confidence in [0,1] so a human can challenge it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal


DecisionType = Literal["ACT_NOW", "DEFER", "MINIMUM_COMPLIANCE"]
ImpactLevel = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass
class Estimate:
    """A single number the engine is not certain about."""
    label: str
    value: float                 # GBP, or FTE-years where noted
    unit: str = "GBP"
    assumption: str = ""
    confidence: float = 0.5      # 0..1 — how much we trust this figure

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class AffectedAsset:
    """One node in the DataHub graph that the regulation touches."""
    urn: str
    name: str
    entity_type: str             # dataset | mlModel | dataFlow | dashboard | chart
    role: str = ""               # why it matters, e.g. "downstream regulatory report"


@dataclass
class Scenario:
    """One of ACT_NOW / DEFER / MINIMUM_COMPLIANCE, fully costed."""
    decision: DecisionType
    cost_of_action: list[Estimate] = field(default_factory=list)
    cost_of_inaction: list[Estimate] = field(default_factory=list)
    opportunity_cost: list[Estimate] = field(default_factory=list)
    duration_months: int = 0
    change_capacity_fte_years: float = 0.0
    displaced_initiative: str = ""
    notes: str = ""

    def total(self, bucket: list[Estimate]) -> float:
        return round(sum(e.value for e in bucket), 2)

    @property
    def action_total(self) -> float:
        return self.total(self.cost_of_action)

    @property
    def inaction_total(self) -> float:
        return self.total(self.cost_of_inaction)

    @property
    def opportunity_total(self) -> float:
        return self.total(self.opportunity_cost)

    @property
    def expected_total_cost(self) -> float:
        """The number the recommendation ranks on: what this path is expected to cost."""
        return round(self.action_total + self.inaction_total + self.opportunity_total, 2)


@dataclass
class Assessment:
    """The Impact & Decision Card. This is also exactly what gets written back."""
    regulation_id: str
    regulation_title: str
    impact: ImpactLevel
    deadline_months: int
    affected_assets: list[AffectedAsset]
    scenarios: list[Scenario]
    recommendation: DecisionType
    rationale: str
    confidence: float
    assessment_date: str

    def as_dict(self) -> dict:
        d = asdict(self)
        return d
