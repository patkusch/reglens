"""Unit tests for reglens.agent.lineage_parser against synthetic response
dicts — fast, no subprocess. The real-process proof lives in
tests/test_mcp_lineage_roundtrip.py; these pin down edge cases precisely.
"""
from __future__ import annotations

from reglens.agent.lineage_parser import parse_lineage_assets

ANCHOR_URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,anchor.thing,PROD)"


def _resp(search_results, key="downstreams"):
    return {key: {"searchResults": search_results, "offset": 0, "returned": len(search_results), "hasMore": False}}


def test_anchor_is_prepended_and_not_duplicated_even_if_present_in_results():
    resp = _resp([
        {"entity": {"urn": ANCHOR_URN, "type": "DATASET", "name": "anchor.thing"}, "degree": 0},
        {"entity": {"urn": "urn:li:dataset:(x,y,PROD)", "type": "DATASET", "name": "y"}, "degree": 1},
    ])
    assets = parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="anchor.thing")
    assert [a.urn for a in assets] == [ANCHOR_URN, "urn:li:dataset:(x,y,PROD)"]


def test_missing_type_defaults_to_dataset_rather_than_raising():
    resp = _resp([{"entity": {"urn": "urn:li:dataset:(x,y,PROD)", "name": "y"}, "degree": 1}])
    assets = parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="anchor.thing")
    assert assets[1].entity_type == "dataset"


def test_unmapped_entity_type_is_lower_camel_cased_not_dropped():
    resp = _resp([{"entity": {"urn": "urn:li:glossaryTerm:(x)", "type": "GLOSSARY_TERM",
                               "properties": {"name": "PII"}}, "degree": 1}])
    assets = parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="anchor.thing")
    assert assets[1].entity_type == "glossaryTerm"


def test_name_falls_back_to_properties_name_then_to_the_urn():
    resp = _resp([
        {"entity": {"urn": "urn:li:dashboard:(looker,dash1)", "type": "DASHBOARD",
                     "properties": {"name": "Dash One"}}, "degree": 1},
        {"entity": {"urn": "urn:li:dashboard:(looker,dash2)", "type": "DASHBOARD"}, "degree": 1},
    ])
    assets = parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="anchor.thing")
    by_urn = {a.urn: a for a in assets}
    assert by_urn["urn:li:dashboard:(looker,dash1)"].name == "Dash One"
    # No name/properties.name at all -> falls back to something derived from the URN,
    # not a crash and not a silently blank name.
    assert by_urn["urn:li:dashboard:(looker,dash2)"].name


def test_degree_bucket_string_sorts_after_real_integers_and_does_not_crash():
    resp = _resp([
        {"entity": {"urn": "urn:li:dataset:(x,far,PROD)", "type": "DATASET", "name": "far"}, "degree": "3+"},
        {"entity": {"urn": "urn:li:dataset:(x,near,PROD)", "type": "DATASET", "name": "near"}, "degree": 1},
    ])
    assets = parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="anchor.thing")
    assert [a.name for a in assets] == ["anchor.thing", "near", "far"]


def test_duplicate_entities_across_results_are_deduplicated_by_urn():
    dup = {"urn": "urn:li:dataset:(x,y,PROD)", "type": "DATASET", "name": "y"}
    resp = _resp([{"entity": dup, "degree": 1}, {"entity": dup, "degree": 2}])
    assets = parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="anchor.thing")
    assert len(assets) == 2


def test_upstream_direction_reads_the_upstreams_key():
    resp = _resp(
        [{"entity": {"urn": "urn:li:dataset:(x,up,PROD)", "type": "DATASET", "name": "up"}, "degree": 1}],
        key="upstreams",
    )
    assets = parse_lineage_assets(
        resp, anchor_urn=ANCHOR_URN, anchor_name="anchor.thing", direction="UPSTREAM"
    )
    assert [a.name for a in assets] == ["anchor.thing", "up"]


def test_malformed_response_missing_the_expected_key_raises_rather_than_silently_empty():
    import pytest

    with pytest.raises(ValueError):
        parse_lineage_assets({"somethingElse": {}}, anchor_urn=ANCHOR_URN, anchor_name="anchor.thing")


def test_empty_search_results_yields_just_the_anchor():
    resp = _resp([])
    assets = parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="anchor.thing")
    assert [a.name for a in assets] == ["anchor.thing"]


def test_role_prefers_properties_description_over_editable_description():
    resp = _resp([{
        "entity": {"urn": "urn:li:dataset:(x,y,PROD)", "type": "DATASET", "name": "y",
                    "properties": {"description": "system desc"},
                    "editableProperties": {"description": "human-edited desc"}},
        "degree": 1,
    }])
    assets = parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="anchor.thing")
    assert assets[1].role == "system desc"


# ── Entity kinds: decided by the URN, in the shapes the real tool returns ───

def _mixed_response():
    """One of each kind, shaped like the real `entityPreview` fragment: Dataset and
    MLModel carry a top-level name (MLModel has no `properties`); Dashboard, Chart
    and DataJob carry only properties.name."""
    flow = "urn:li:dataFlow:(airflow,nightly,PROD)"
    return _resp([
        {"entity": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,t.orders,PROD)",
                    "type": "DATASET", "name": "t.orders",
                    "properties": {"name": "t.orders", "description": "Orders."}}, "degree": 1},
        {"entity": {"urn": "urn:li:dashboard:(powerbi,board_pack)", "type": "DASHBOARD",
                    "tool": "powerbi", "dashboardId": "board_pack",
                    "properties": {"name": "Board Pack", "description": "For the board."}}, "degree": 1},
        {"entity": {"urn": "urn:li:mlModel:(urn:li:dataPlatform:mlflow,churn_v3,PROD)",
                    "type": "ML_MODEL", "name": "churn_v3", "description": "Churn model.",
                    "origin": "PROD"}, "degree": 2},
        {"entity": {"urn": f"urn:li:dataJob:({flow},load_orders)", "type": "DATA_JOB",
                    "jobId": "load_orders", "dataFlow": {"urn": flow, "flowId": "nightly"},
                    "properties": {"name": "load_orders", "description": "Loads orders."}}, "degree": 2},
        {"entity": {"urn": "urn:li:chart:(looker,orders_by_day)", "type": "CHART",
                    "properties": {"name": "orders_by_day"}}, "degree": 3},
    ])


def test_a_response_mixing_all_kinds_parses_kind_name_and_role_for_each():
    assets = parse_lineage_assets(_mixed_response(), anchor_urn=ANCHOR_URN, anchor_name="anchor.thing")
    by_name = {a.name: a for a in assets}
    assert {n: a.entity_type for n, a in by_name.items() if n != "anchor.thing"} == {
        "t.orders": "dataset", "Board Pack": "dashboard", "churn_v3": "mlModel",
        "load_orders": "dataJob", "orders_by_day": "chart",
    }
    # An MLModel keeps its description at the top level, not under `properties`.
    assert by_name["churn_v3"].role == "Churn model."
    assert by_name["Board Pack"].role == "For the board."
    assert by_name["load_orders"].role == "Loads orders."
    for a in assets:
        assert a.urn.startswith(f"urn:li:{a.entity_type}:"), a


def test_kind_comes_from_the_urn_not_from_the_type_enum_or_a_subtype_tag():
    resp = _resp([
        # A dataset that carries the old "Dashboard" subtype tag stays a dataset.
        {"entity": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,dash.fake,PROD)",
                    "type": "DATASET", "name": "dash.fake",
                    "subTypes": {"typeNames": ["Dashboard"]}}, "degree": 1},
        # If the enum and the URN ever disagree, the URN is DataHub's identity.
        {"entity": {"urn": "urn:li:mlModel:(urn:li:dataPlatform:mlflow,m,PROD)",
                    "type": "DATASET", "name": "m"}, "degree": 1},
        # No `type` at all: the URN is enough.
        {"entity": {"urn": "urn:li:dashboard:(powerbi,d)", "properties": {"name": "d"}}, "degree": 1},
    ])
    by_name = {a.name: a for a in parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="a")}
    assert by_name["dash.fake"].entity_type == "dataset"
    assert by_name["m"].entity_type == "mlModel"
    assert by_name["d"].entity_type == "dashboard"


def test_the_type_enum_is_only_a_fallback_for_an_unreadable_urn():
    resp = _resp([{"entity": {"urn": "not-a-urn", "type": "ML_MODEL", "name": "m"}, "degree": 1}])
    assets = parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="a")
    assert assets[1].entity_type == "mlModel"


def test_names_decoded_from_the_urn_when_nothing_else_names_the_entity():
    flow = "urn:li:dataFlow:(airflow,nightly,PROD)"
    resp = _resp([
        {"entity": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,db.t,PROD)"}, "degree": 1},
        {"entity": {"urn": "urn:li:mlModel:(urn:li:dataPlatform:mlflow,scorer,PROD)"}, "degree": 1},
        {"entity": {"urn": "urn:li:dashboard:(powerbi,board)"}, "degree": 1},
        {"entity": {"urn": "urn:li:chart:(looker,orders)"}, "degree": 1},
        # A job's URN nests its flow's; the name is the job, not the flow.
        {"entity": {"urn": f"urn:li:dataJob:({flow},load)"}, "degree": 1},
    ])
    kinds = {a.entity_type: a.name for a in parse_lineage_assets(resp, anchor_urn=ANCHOR_URN, anchor_name="a")[1:]}
    assert kinds == {"dataset": "db.t", "mlModel": "scorer", "dashboard": "board",
                     "chart": "orders", "dataJob": "load"}


def test_the_anchor_kind_also_comes_from_its_urn():
    assets = parse_lineage_assets(
        _resp([]), anchor_urn="urn:li:dashboard:(powerbi,board)", anchor_name="board"
    )
    assert assets[0].entity_type == "dashboard"


def test_the_seeded_graph_served_in_real_shapes_parses_to_the_deterministic_closure():
    # Serve Northstar itself in the real per-type shapes and parse it: the URN
    # forms graph.py uses and the kinds the parser reads must agree, or the
    # deterministic fallback and the MCP path would disagree about the same graph.
    from reglens.agent.reglens_agent import ANCHOR, discover_impact_deterministic
    from reglens.seed import graph

    expected = discover_impact_deterministic()
    results = []
    for a in expected[1:]:
        entity = {"urn": a.urn, "type": {"dataset": "DATASET", "dashboard": "DASHBOARD",
                                          "mlModel": "ML_MODEL", "dataJob": "DATA_JOB"}[a.entity_type]}
        if a.entity_type in ("dataset", "mlModel"):
            entity["name"] = a.name
        else:
            entity["properties"] = {"name": a.name}
        entity.setdefault("properties", {})["description"] = a.role
        results.append({"entity": entity, "degree": 1})
    parsed = parse_lineage_assets(
        _resp(results), anchor_urn=graph.urn_for(ANCHOR), anchor_name=ANCHOR,
        anchor_role=expected[0].role,
    )
    key = lambda a: (a.urn, a.name, a.entity_type, a.role)  # noqa: E731
    assert sorted(map(key, parsed)) == sorted(map(key, expected))
