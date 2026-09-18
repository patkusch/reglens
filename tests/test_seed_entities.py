"""The seeded graph as real DataHub entities, and the write-back onto them.

No DataHub server is needed: the seed script's `build_plan()` builds the exact SDK
entities it would send, so these tests read their URNs and aspects directly, and
the write-back is run against a stand-in client that hands back real SDK entities
(rebuilt from those aspects, the way `client.entities.get` rebuilds them from a
server) and records what would be sent.
"""
from __future__ import annotations

import pytest

pytest.importorskip("datahub.sdk", reason="acryl-datahub is a core requirement (requirements.txt)")

from datahub.metadata import schema_classes as models  # noqa: E402
from datahub.metadata.urns import Urn  # noqa: E402
from datahub.sdk import Dashboard, DataFlow, DataJob, Dataset, MLModel  # noqa: E402
from datahub.sdk.entity_client import ENTITY_CLASSES  # noqa: E402

from reglens.agent.reglens_agent import build_assessment, discover_impact_deterministic  # noqa: E402
from reglens.agent.writeback import write_assessment_via_sdk  # noqa: E402
from reglens.engine.impact_card import writeback_payload  # noqa: E402
from reglens.seed import graph  # noqa: E402
from reglens.seed.seed_northstar import build_plan  # noqa: E402


@pytest.fixture(scope="module")
def plan():
    return build_plan()


def _aspects(entity) -> dict:
    return {m.aspect.ASPECT_NAME: m.aspect for m in entity.as_mcps()}


class TestSeededEntities:
    def test_each_asset_is_the_datahub_entity_its_kind_says(self, plan):
        by_urn = {str(e.urn): e for e in plan.entities}
        expected_class = {"dataset": Dataset, "dashboard": Dashboard, "mlModel": MLModel, "dataJob": DataJob}
        for name, kind, *_ in graph.ASSETS:
            etype = graph.KIND_TO_ENTITY[kind]
            entity = by_urn[graph.urn_for(name)]
            assert type(entity) is expected_class[etype], name
            assert entity.urn.entity_type == etype, name
        # Every pipeline is a DataFlow holding a DataJob.
        for name, kind, *_ in graph.ASSETS:
            if kind == "Pipeline":
                assert type(by_urn[graph.data_flow_urn(name)]) is DataFlow, name

    def test_nothing_that_should_be_a_dashboard_or_model_is_still_a_dataset(self, plan):
        datasets = {str(e.urn) for e in plan.entities if isinstance(e, Dataset)}
        assert datasets == {graph.dataset_urn(n) for n, k, *_ in graph.ASSETS if k == "Table"}
        assert not [u for u in datasets if "dash." in u or "ml." in u or "pipe." in u]

    def test_graph_py_urns_are_exactly_the_urns_the_sdk_builds(self, plan):
        # graph.py builds URN strings with no SDK; this pins them to the SDK's own.
        sdk_urns = {str(e.urn) for e in plan.entities}
        graph_urns = {graph.urn_for(n) for n, *_ in graph.ASSETS} | {
            graph.data_flow_urn(n) for n, k, *_ in graph.ASSETS if k == "Pipeline"
        }
        assert sdk_urns == graph_urns
        assert Urn.from_string(graph.urn_for("ml.risk_scoring_model")).entity_type == "mlModel"

    def test_dashboards_and_the_model_carry_their_own_aspects(self, plan):
        by_urn = {str(e.urn): e for e in plan.entities}
        dash = _aspects(by_urn[graph.dashboard_urn("dash.risk_committee_report")])
        assert isinstance(dash["dashboardInfo"], models.DashboardInfoClass)
        assert dash["dashboardInfo"].title == "dash.risk_committee_report"
        model = _aspects(by_urn[graph.ml_model_urn("ml.risk_scoring_model")])
        assert isinstance(model["mlModelProperties"], models.MLModelPropertiesClass)
        assert model["mlModelProperties"].description.startswith("Model that assigns risk tiers")
        assert "datasetProperties" not in model and "schemaMetadata" not in model

    def test_the_seed_stores_exactly_the_lineage_graph_py_declares(self, plan):
        stored: set[tuple[str, str]] = set(plan.dataset_edges)
        for entity in plan.entities:
            me = str(entity.urn)
            for aspect in _aspects(entity).values():
                if isinstance(aspect, models.DashboardInfoClass):
                    stored |= {(e.destinationUrn, me) for e in aspect.datasetEdges or []}
                    stored |= {(u, me) for u in aspect.datasets or []}
                elif isinstance(aspect, models.DataJobInputOutputClass):
                    stored |= {(u, me) for u in aspect.inputDatasets or []}
                    stored |= {(e.destinationUrn, me) for e in aspect.inputDatasetEdges or []}
                    stored |= {(me, u) for u in aspect.outputDatasets or []}
                elif isinstance(aspect, models.MLModelPropertiesClass):
                    stored |= {(j, me) for j in aspect.trainingJobs or []}
                    stored |= {(me, j) for j in aspect.downstreamJobs or []}
        declared = {(graph.urn_for(up), graph.urn_for(down)) for up, down in graph.LINEAGE}
        assert stored == declared

    def test_the_model_is_reached_through_a_training_job_and_left_through_a_scoring_job(self, plan):
        model = _aspects({str(e.urn): e for e in plan.entities}[graph.ml_model_urn("ml.risk_scoring_model")])
        props = model["mlModelProperties"]
        assert props.trainingJobs == [graph.data_job_urn("pipe.risk_model_training")]
        assert props.downstreamJobs == [graph.data_job_urn("pipe.risk_scoring_pipeline")]


class _FakeEntities:
    def __init__(self, plan, sent):
        self._by_urn = {str(e.urn): e for e in plan.entities}
        self._sent = sent

    def get(self, urn):
        # What `client.entities.get` does: pick the class from the URN's entity type
        # and rebuild it from the stored aspects.
        parsed = Urn.from_string(urn)
        seeded = self._by_urn[str(urn)]
        return ENTITY_CLASSES[parsed.entity_type]._new_from_graph(parsed, _aspects(seeded))

    def update(self, entity):
        self._sent.append(entity)


class _FakeClient:
    def __init__(self, plan):
        self.sent: list = []
        self.entities = _FakeEntities(plan, self.sent)


class TestWriteBack:
    def test_each_target_is_written_as_its_own_entity_type(self, plan):
        assessment = build_assessment("RCS-2026", discover_impact_deterministic())
        payload = writeback_payload(assessment)
        client = _FakeClient(plan)

        updated = write_assessment_via_sdk(payload, client=client)

        assert updated == payload["targets"], "every target was written"
        by_urn = {str(e.urn): e for e in client.sent}
        assert set(by_urn) == set(payload["targets"])
        expected_class = {"dataset": Dataset, "dashboard": Dashboard, "mlModel": MLModel, "dataJob": DataJob}
        for asset in assessment.affected_assets:
            assert type(by_urn[asset.urn]) is expected_class[asset.entity_type], asset.name

    def test_the_assessment_lands_on_each_entitys_own_description_and_glossary_aspects(self, plan):
        assessment = build_assessment("RCS-2026", discover_impact_deterministic())
        payload = writeback_payload(assessment)
        client = _FakeClient(plan)
        write_assessment_via_sdk(payload, client=client)

        term_urn = f"urn:li:glossaryTerm:{payload['glossary_term']}"
        for entity in client.sent:
            mcps = entity.as_mcps()
            assert {m.entityUrn for m in mcps} == {str(entity.urn)}
            assert {m.entityType for m in mcps} == {entity.urn.entity_type}
            described = [m.aspect for m in mcps if getattr(m.aspect, "description", None) == payload["description"]]
            assert described, f"description missing on {entity.urn}"
            terms = [t.urn for m in mcps if isinstance(m.aspect, models.GlossaryTermsClass) for t in m.aspect.terms]
            assert term_urn in terms, f"glossary term missing on {entity.urn}"

        by_type = {}
        for entity in client.sent:
            by_type.setdefault(entity.urn.entity_type, []).append(entity)
        assert {t: len(v) for t, v in by_type.items()} == {"dataset": 3, "mlModel": 1, "dataJob": 3, "dashboard": 3}
        mlm = _aspects(by_type["mlModel"][0])
        assert mlm["mlModelProperties"].description == payload["description"]
        dash = _aspects(by_type["dashboard"][0])
        assert dash["dashboardInfo"].description == payload["description"]
