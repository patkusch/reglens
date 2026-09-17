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
