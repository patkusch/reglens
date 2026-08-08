"""Transparent, deterministic scenario engine.

Deliberately NOT a sophisticated financial model. It is a *glass-box* that turns
a handful of named assumptions into three costed paths, so a human can argue with
every number. Swap the constants for your own; the point is the reasoning is legible.

    cost of action      = people + technology + vendor + programme
    cost of inaction    = P(penalty) x consequence  (+ remediation + future uplift)
    opportunity cost    = value of the displaced strategic initiative
"""
from __future__ import annotations

from reglens.models import AffectedAsset, Assessment, Estimate, Scenario

# ---- Tunable assumptions (GBP). Edit freely; each surfaces in the card. ----
COST_PER_AFFECTED_ASSET = 180_000        # eng + analysis to touch one asset
ML_MODEL_REBUILD_COST = 1_600_000        # retrain + revalidate a production risk model
REPORT_RECERT_COST = 250_000             # re-certify one regulatory report/dashboard
VENDOR_COST_FULL = 700_000               # external methodology / assurance
PROGRAMME_OVERHEAD = 0.20                # PMO/change on top of build

FTE_COST_PER_YEAR = 120_000
DISPLACED_INITIATIVE = "Core Banking Migration"
DISPLACED_INITIATIVE_VALUE = 5_000_000   # value at risk if it slips 6 months

# Inaction (delay 6 months) assumptions
P_SUPERVISORY_PENALTY = 0.35             # probability a penalty crystallises
PENALTY_CONSEQUENCE = 6_000_000          # headline penalty if it does
REMEDIATION_LOW, REMEDIATION_HIGH = 1_100_000, 3_500_000
FUTURE_IMPL_UPLIFT = 0.12                # implementation gets ~12% dearer if deferred


def _is_ml(asset: AffectedAsset) -> bool:
    return asset.entity_type.lower() in {"mlmodel", "ml model", "ml.model"} or \
        "model" in asset.name.lower()


def _is_report(asset: AffectedAsset) -> bool:
    n = asset.name.lower()
    return any(k in n for k in ("report", "dashboard", "submission", "pack"))


def build_scenarios(
    assets: list[AffectedAsset],
    deadline_months: int,
) -> list[Scenario]:
    n_assets = len(assets)
    n_reports = sum(1 for a in assets if _is_report(a))
    ml_in_scope = any(_is_ml(a) for a in assets)

    base_people = n_assets * COST_PER_AFFECTED_ASSET
    ml_cost = ML_MODEL_REBUILD_COST if ml_in_scope else 0
    report_cost = n_reports * REPORT_RECERT_COST
    build = base_people + ml_cost + report_cost + VENDOR_COST_FULL
    programme = round(build * PROGRAMME_OVERHEAD)
    full_impl = build + programme

    remediation_mid = (REMEDIATION_LOW + REMEDIATION_HIGH) / 2

    # ---------- ACT NOW ----------
    act = Scenario(
        decision="ACT_NOW",
        duration_months=min(deadline_months, 9),
        change_capacity_fte_years=round(full_impl / FTE_COST_PER_YEAR),
        displaced_initiative=DISPLACED_INITIATIVE,
        notes="Full methodology rebuild incl. model revalidation. Compliant on time.",
        cost_of_action=[
            Estimate("People / engineering", base_people, assumption=f"{n_assets} affected assets x £{COST_PER_AFFECTED_ASSET:,}", confidence=0.6),
            Estimate("Model rebuild + revalidation", ml_cost, assumption="Retrain + independent validation of production risk model", confidence=0.45 if ml_in_scope else 0.9),
            Estimate("Report re-certification", report_cost, assumption=f"{n_reports} regulatory reports/dashboards x £{REPORT_RECERT_COST:,}", confidence=0.6),
            Estimate("Vendor / assurance", VENDOR_COST_FULL, assumption="External methodology + assurance", confidence=0.55),
            Estimate("Programme overhead", programme, assumption=f"{int(PROGRAMME_OVERHEAD*100)}% PMO/change", confidence=0.7),
        ],
        cost_of_inaction=[
            Estimate("Regulatory penalty exposure", 0, assumption="Compliant on time — no penalty exposure", confidence=0.85),
        ],
        opportunity_cost=[
            Estimate(f"Displaces {DISPLACED_INITIATIVE}", DISPLACED_INITIATIVE_VALUE, assumption="Full capacity draw slips the strategic programme ~6 months", confidence=0.5),
        ],
    )

    # ---------- MINIMUM COMPLIANCE ----------
    # Patch classification rules; defer full model rebuild. ~45% of full build.
    min_build = round((base_people + report_cost) * 0.55 + VENDOR_COST_FULL * 0.4)
    min_programme = round(min_build * PROGRAMME_OVERHEAD)
    min_impl = min_build + min_programme
    residual_risk = round(P_SUPERVISORY_PENALTY * 0.4 * PENALTY_CONSEQUENCE)
    minimum = Scenario(
        decision="MINIMUM_COMPLIANCE",
        duration_months=min(deadline_months, 5),
        change_capacity_fte_years=round(min_impl / FTE_COST_PER_YEAR),
        displaced_initiative="Partial — strategic capacity largely preserved",
        notes="Meets the letter via rule patch; full model rebuild scheduled later.",
        cost_of_action=[
            Estimate("People / engineering (scoped)", round((base_people) * 0.55), assumption="Rule-level changes, no full model rebuild", confidence=0.5),
            Estimate("Report re-certification", round(report_cost * 0.55), assumption="Re-cert only directly-affected reports", confidence=0.55),
            Estimate("Vendor (limited)", round(VENDOR_COST_FULL * 0.4), assumption="Lighter external assurance", confidence=0.5),
            Estimate("Programme overhead", min_programme, assumption=f"{int(PROGRAMME_OVERHEAD*100)}% PMO/change", confidence=0.7),
        ],
        cost_of_inaction=[
            Estimate("Residual supervisory risk", residual_risk, assumption="Reduced but non-zero risk of a methodology finding", confidence=0.4),
        ],
        opportunity_cost=[
            Estimate("Strategic capacity preserved", round(DISPLACED_INITIATIVE_VALUE * 0.2), assumption="Minor draw on the strategic programme", confidence=0.5),
        ],
    )

    # ---------- DEFER 6 MONTHS ----------
    delay_penalty = round(P_SUPERVISORY_PENALTY * PENALTY_CONSEQUENCE)
    future_uplift = round(full_impl * FUTURE_IMPL_UPLIFT)
    defer = Scenario(
        decision="DEFER",
        duration_months=deadline_months,
        change_capacity_fte_years=0.0,
        displaced_initiative="None now — capacity preserved short term",
        notes="Do nothing for 6 months. Carries penalty + remediation + cost uplift.",
        cost_of_action=[
            Estimate("Near-term build", 0, assumption="No build in the deferral window", confidence=0.9),
            Estimate("Future implementation uplift", future_uplift, assumption=f"~{int(FUTURE_IMPL_UPLIFT*100)}% dearer once deferred", confidence=0.4),
        ],
        cost_of_inaction=[
            Estimate("Expected penalty", delay_penalty, assumption=f"P(penalty)={P_SUPERVISORY_PENALTY} x £{PENALTY_CONSEQUENCE:,}", confidence=0.35),
            Estimate("Remediation (mid)", round(remediation_mid), assumption=f"Range £{REMEDIATION_LOW:,}–£{REMEDIATION_HIGH:,}", confidence=0.35),
        ],
        opportunity_cost=[
            Estimate("Strategic capacity preserved", 0, assumption="No displacement in the window", confidence=0.7),
        ],
    )

    return [act, minimum, defer]


def recommend(scenarios: list[Scenario]) -> tuple[str, str, float]:
    """Pick the lowest expected-total-cost path. Returns (decision, rationale, confidence)."""
    ranked = sorted(scenarios, key=lambda s: s.expected_total_cost)
    best, second = ranked[0], ranked[1]
    margin = second.expected_total_cost - best.expected_total_cost
    # Confidence in the *ranking* scales with how clear the margin is, tempered by
    # the average confidence of the winning path's estimates.
    est = [e for b in (best.cost_of_action, best.cost_of_inaction, best.opportunity_cost) for e in b]
    avg_conf = sum(e.confidence for e in est) / max(len(est), 1)
    clarity = min(margin / max(best.expected_total_cost, 1), 1.0)
    confidence = round(0.5 * avg_conf + 0.5 * (0.4 + 0.6 * clarity), 2)
    rationale = (
        f"{best.decision} has the lowest expected total cost "
        f"(£{best.expected_total_cost:,.0f}) vs next-best {second.decision} "
        f"(£{second.expected_total_cost:,.0f}); margin £{margin:,.0f}. {best.notes}"
    )
    return best.decision, rationale, confidence
