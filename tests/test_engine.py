"""The glass box, checked: the graph the agent walks, the arithmetic behind every
scenario, the recommendation rule, the card, and the committed example.

No DataHub, no MCP, no network — everything here is the deterministic path the
demo falls back to, which is also the path a reviewer can re-run by hand.
"""
from __future__ import annotations

import json
from pathlib import Path

from reglens.agent.reglens_agent import ANCHOR, build_assessment, discover_impact_deterministic
from reglens.engine import scenario_engine as se
from reglens.engine.impact_card import render_markdown, render_text, to_json, writeback_payload
from reglens.models import AffectedAsset
from reglens.seed import graph

ROOT = Path(__file__).resolve().parent.parent


_URN_FOR_TYPE = {
    "dataset": graph.dataset_urn,
    "dashboard": graph.dashboard_urn,
    "mlModel": graph.ml_model_urn,
    "dataJob": graph.data_job_urn,
}


def asset(name: str, entity_type: str = "dataset") -> AffectedAsset:
    return AffectedAsset(urn=_URN_FOR_TYPE[entity_type](name), name=name, entity_type=entity_type, role="test")


# ── The seeded graph ────────────────────────────────────────────────────────

class TestGraph:
    def test_every_lineage_edge_joins_two_known_assets(self):
        names = {a[0] for a in graph.ASSETS}
        assert len(names) == len(graph.ASSETS), "asset names are unique"
        for up, down in graph.LINEAGE:
            assert up in names and down in names, (up, down)
        for name, kind, _desc, fields, owner in graph.ASSETS:
            assert kind in graph.KIND_TO_ENTITY, name
            assert fields and owner, name

    def test_every_lineage_edge_is_one_datahub_can_store(self):
        # No invented edges: a model has no dataset parent and a dashboard has no job
        # parent in DataHub, so the seed must route them through the entities DataHub
        # actually links (a training job for the model).
        for up, down in graph.LINEAGE:
            pair = (graph.entity_type_of(up), graph.entity_type_of(down))
            assert pair in graph.DATAHUB_LINEAGE_EDGES, (up, down, pair)
        assert ("dataset", "mlModel") not in graph.DATAHUB_LINEAGE_EDGES

    def test_lineage_is_acyclic(self):
        adj: dict[str, list[str]] = {}
        for up, down in graph.LINEAGE:
            adj.setdefault(up, []).append(down)
        state: dict[str, int] = {}

        def visit(n: str) -> None:
            assert state.get(n) != 1, f"cycle through {n}"
            if state.get(n) == 2:
                return
            state[n] = 1
            for m in adj.get(n, []):
                visit(m)
            state[n] = 2

        for n in adj:
            visit(n)

    def test_downstream_closure_is_the_chain_the_readme_describes(self):
        names = [a.name for a in discover_impact_deterministic()]
        assert names[0] == ANCHOR
        assert len(names) == len(set(names)), "no asset twice"
        for must in ("pipe.risk_model_training", "ml.risk_scoring_model", "report.regulatory_risk_report",
                     "dash.supervisory_submission_pack", "dash.capital_reporting_dashboard",
                     "dash.risk_committee_report"):
            assert must in names, must
        # Upstream inputs are not impacted assets, and neither are siblings that
        # only feed the report from the side.
        for must_not in ("retail.customer", "risk.customer_kyc", "risk.exposure_positions",
                         "risk.customer_segmentation", "risk.transaction_monitoring_alerts"):
            assert must_not not in names, must_not
        assert names == [a.name for a in discover_impact_deterministic()], "deterministic order"

    def test_assets_carry_datahub_entity_types_and_urns(self):
        by_name = {a.name: a for a in discover_impact_deterministic()}
        expected = {
            ANCHOR: ("dataset", f"urn:li:dataset:(urn:li:dataPlatform:snowflake,{ANCHOR},PROD)"),
            "report.regulatory_risk_report": (
                "dataset",
                "urn:li:dataset:(urn:li:dataPlatform:snowflake,report.regulatory_risk_report,PROD)"),
            "ml.risk_scoring_model": (
                "mlModel", "urn:li:mlModel:(urn:li:dataPlatform:mlflow,ml.risk_scoring_model,PROD)"),
            "dash.supervisory_submission_pack": (
                "dashboard", "urn:li:dashboard:(powerbi,dash.supervisory_submission_pack)"),
            "dash.capital_reporting_dashboard": (
                "dashboard", "urn:li:dashboard:(powerbi,dash.capital_reporting_dashboard)"),
            "pipe.risk_model_training": (
                "dataJob",
                "urn:li:dataJob:(urn:li:dataFlow:(airflow,pipe.risk_model_training,PROD),pipe.risk_model_training)"),
            "pipe.risk_scoring_pipeline": (
                "dataJob",
                "urn:li:dataJob:(urn:li:dataFlow:(airflow,pipe.risk_scoring_pipeline,PROD),pipe.risk_scoring_pipeline)"),
        }
        for name, (kind, urn) in expected.items():
            assert (by_name[name].entity_type, by_name[name].urn) == (kind, urn), name

    def test_every_assets_kind_is_the_entity_type_in_its_own_urn(self):
        for a in discover_impact_deterministic():
            assert a.urn.startswith(f"urn:li:{a.entity_type}:"), (a.name, a.urn)
        counts: dict[str, int] = {}
        for a in discover_impact_deterministic():
            counts[a.entity_type] = counts.get(a.entity_type, 0) + 1
        assert counts == {"dataset": 3, "mlModel": 1, "dataJob": 3, "dashboard": 3}


# ── The scenario arithmetic ─────────────────────────────────────────────────

ASSETS = [asset("risk.customer_risk_profile"), asset("ml.risk_scoring_model", "mlModel"),
          asset("report.regulatory_risk_report"), asset("dash.supervisory_submission_pack", "dashboard")]


class TestScenarios:
    def test_act_now_is_the_sum_of_its_named_assumptions(self):
        act, _, _ = se.build_scenarios(ASSETS, 12)
        base = 4 * se.COST_PER_AFFECTED_ASSET
        reports = 2 * se.REPORT_RECERT_COST          # "report" and "pack" in the names
        build = base + se.ML_MODEL_REBUILD_COST + reports + se.VENDOR_COST_FULL
        programme = round(build * se.PROGRAMME_OVERHEAD)
        assert act.action_total == build + programme
        assert act.inaction_total == 0
        assert act.opportunity_total == se.DISPLACED_INITIATIVE_VALUE
        assert act.duration_months == 9 and act.change_capacity_fte_years == round((build + programme) / se.FTE_COST_PER_YEAR)

    def test_defer_carries_the_expected_penalty_the_remediation_and_the_uplift(self):
        act, _, defer = se.build_scenarios(ASSETS, 12)
        assert defer.action_total == round(act.action_total * se.FUTURE_IMPL_UPLIFT)
        assert defer.inaction_total == round(se.P_SUPERVISORY_PENALTY * se.PENALTY_CONSEQUENCE) + \
            round((se.REMEDIATION_LOW + se.REMEDIATION_HIGH) / 2)
        assert defer.opportunity_total == 0
        assert defer.duration_months == 12 and defer.change_capacity_fte_years == 0

    def test_minimum_compliance_is_the_scoped_fraction_with_residual_risk(self):
        _, minimum, _ = se.build_scenarios(ASSETS, 12)
        base = 4 * se.COST_PER_AFFECTED_ASSET
        reports = 2 * se.REPORT_RECERT_COST
        scoped = round(base * 0.55) + round(reports * 0.55) + round(se.VENDOR_COST_FULL * 0.4)
        programme = round(round((base + reports) * 0.55 + se.VENDOR_COST_FULL * 0.4) * se.PROGRAMME_OVERHEAD)
        assert minimum.action_total == scoped + programme
        assert minimum.inaction_total == round(se.P_SUPERVISORY_PENALTY * 0.4 * se.PENALTY_CONSEQUENCE)
        assert minimum.opportunity_total == round(se.DISPLACED_INITIATIVE_VALUE * 0.2)
        assert minimum.duration_months == 5

    def test_model_and_reports_are_found_by_entity_type_not_by_name(self):
        # A model is an mlModel entity whatever it is called, and a dataset that only
        # has "model" in its name is not one. A pipeline named "...reporting..." is a
        # job, not a report; a dashboard is a report whatever it is called.
        named_model_but_dataset = [asset("risk.model_inputs")]
        assert se.build_scenarios(named_model_but_dataset, 12)[0].cost_of_action[1].value == 0
        model_by_type = [asset("x.scorer", "mlModel")]
        assert se.build_scenarios(model_by_type, 12)[0].cost_of_action[1].value == se.ML_MODEL_REBUILD_COST

        job_named_reporting = [asset("pipe.capital_reporting_pipeline", "dataJob")]
        assert se.build_scenarios(job_named_reporting, 12)[0].cost_of_action[2].value == 0
        dashboard_by_type = [asset("x.exec_view", "dashboard")]
        assert se.build_scenarios(dashboard_by_type, 12)[0].cost_of_action[2].value == se.REPORT_RECERT_COST

    def test_no_model_in_scope_means_no_rebuild_cost_and_a_confident_zero(self):
        act, _, _ = se.build_scenarios([asset("risk.customer_risk_profile")], 12)
        rebuild = next(e for e in act.cost_of_action if e.label.startswith("Model rebuild"))
        assert rebuild.value == 0 and rebuild.confidence == 0.9
        with_model, _, _ = se.build_scenarios([asset("x", "mlModel")], 12)
        rebuild = next(e for e in with_model.cost_of_action if e.label.startswith("Model rebuild"))
        assert rebuild.value == se.ML_MODEL_REBUILD_COST and rebuild.confidence < 0.5

    def test_every_figure_carries_an_assumption_and_a_confidence_and_totals_add_up(self):
        for s in se.build_scenarios(ASSETS, 12):
            buckets = (s.cost_of_action, s.cost_of_inaction, s.opportunity_cost)
            for e in (e for b in buckets for e in b):
                assert e.assumption, f"{s.decision}: {e.label} has no assumption"
                assert 0.0 <= e.confidence <= 1.0, f"{s.decision}: {e.label}"
            assert s.expected_total_cost == round(s.action_total + s.inaction_total + s.opportunity_total, 2)
            assert s.duration_months <= 12

    def test_a_short_deadline_caps_every_duration(self):
        for s in se.build_scenarios(ASSETS, 3):
            assert s.duration_months <= 3


# ── The recommendation rule ─────────────────────────────────────────────────

class TestRecommend:
    def test_picks_the_lowest_expected_total_and_says_why(self):
        scenarios = se.build_scenarios(ASSETS, 12)
        decision, rationale, confidence = se.recommend(scenarios)
        cheapest = min(scenarios, key=lambda s: s.expected_total_cost)
        second = sorted(scenarios, key=lambda s: s.expected_total_cost)[1]
        assert decision == cheapest.decision
        assert cheapest.decision in rationale and second.decision in rationale
        assert 0.0 <= confidence <= 1.0
        assert se.recommend(scenarios) == (decision, rationale, confidence), "deterministic"

    def test_a_clearer_margin_gives_more_confidence(self):
        s1 = se.build_scenarios(ASSETS, 12)
        # Shrink the margin: make the runner-up as cheap as the winner.
        ranked = sorted(s1, key=lambda s: s.expected_total_cost)
        ranked[1].cost_of_action = [se.Estimate("x", ranked[0].expected_total_cost, assumption="tie", confidence=0.5)]
        ranked[1].cost_of_inaction, ranked[1].opportunity_cost = [], []
        _, _, tight = se.recommend(s1)
        _, _, clear = se.recommend(se.build_scenarios(ASSETS, 12))
        assert tight < clear


# ── The card, the write-back, and the committed example ─────────────────────

class TestCard:
    def test_writeback_targets_every_affected_asset_with_a_queryable_term(self):
        a = build_assessment("RCS-2026", discover_impact_deterministic())
        p = writeback_payload(a)
        assert p["glossary_term"] == f"RegLens.RCS-2026.{a.recommendation}"
        assert p["targets"] == [x.urn for x in a.affected_assets]
        assert a.regulation_id in p["description"] and a.recommendation in p["description"]

    def test_writeback_targets_are_typed_urns_one_per_asset_matching_the_card(self):
        a = build_assessment("RCS-2026", discover_impact_deterministic())
        targets = writeback_payload(a)["targets"]
        assert len(set(targets)) == len(a.affected_assets)
        for asset_, urn in zip(a.affected_assets, targets):
            assert urn.split(":")[2] == asset_.entity_type, (asset_.name, urn)
        assert "urn:li:mlModel:(urn:li:dataPlatform:mlflow,ml.risk_scoring_model,PROD)" in targets
        assert "urn:li:dashboard:(powerbi,dash.risk_committee_report)" in targets
        assert not any(t.startswith("urn:li:dataset:") and ("dash." in t or "ml." in t or "pipe." in t)
                       for t in targets), "nothing is still a dataset stand-in"

    def test_renderings_show_every_scenario_and_the_recommendation(self):
        a = build_assessment("RCS-2026", discover_impact_deterministic())
        for text in (render_text(a), render_markdown(a)):
            for s in a.scenarios:
                assert s.decision in text and f"£{s.expected_total_cost:,.0f}" in text
            assert a.recommendation in text
        parsed = json.loads(to_json(a))
        assert [s["decision"] for s in parsed["scenarios"]] == ["ACT_NOW", "MINIMUM_COMPLIANCE", "DEFER"]

    def test_impact_level_follows_the_size_of_the_blast_radius(self):
        assert build_assessment("RCS-2026", discover_impact_deterministic()).impact == "HIGH"
        assert build_assessment("RCS-2026", ASSETS).impact == "MEDIUM"

    def test_the_committed_example_is_what_the_code_produces(self):
        # examples/sample_assessment.json is shown to judges. If the engine drifts,
        # this fails before the example lies.
        sample = json.loads((ROOT / "examples" / "sample_assessment.json").read_text())
        a = build_assessment("RCS-2026", discover_impact_deterministic())
        assert [x.name for x in a.affected_assets] == [x["name"] for x in sample["affected_assets"]]
        assert a.recommendation == sample["recommendation"]
        assert a.confidence == sample["confidence"]
        assert a.impact == sample["impact"]
        for fresh, old in zip(a.scenarios, sample["scenarios"]):
            assert fresh.decision == old["decision"]
            assert fresh.action_total == round(sum(e["value"] for e in old["cost_of_action"]), 2)
            assert fresh.inaction_total == round(sum(e["value"] for e in old["cost_of_inaction"]), 2)
            assert fresh.opportunity_total == round(sum(e["value"] for e in old["opportunity_cost"]), 2)
