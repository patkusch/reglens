import dataclasses

import pytest

from reglens.seed.regulations import RCS_2026, REGULATIONS, Regulation


def test_the_registry_is_keyed_by_each_regulations_own_id():
    assert REGULATIONS
    for key, reg in REGULATIONS.items():
        assert key == reg.id


def test_the_demo_regulation_is_marked_fictional_so_nobody_mistakes_it_for_a_real_rule():
    assert "fictional" in RCS_2026.issuer.lower()
    assert RCS_2026 in REGULATIONS.values()


def test_a_regulation_cannot_be_edited_after_it_is_defined():
    with pytest.raises(dataclasses.FrozenInstanceError):
        RCS_2026.deadline_months = 1  # type: ignore[misc]


def test_every_regulation_has_a_title_a_summary_a_deadline_and_things_to_search_for():
    for reg in REGULATIONS.values():
        assert isinstance(reg, Regulation)
        assert reg.title.strip() and reg.summary.strip()
        assert reg.deadline_months > 0
        assert reg.seed_search_terms
        assert all(t.strip() for t in reg.seed_search_terms)


def test_search_terms_are_unique_and_lower_case():
    terms = RCS_2026.seed_search_terms
    assert len(set(terms)) == len(terms)
    assert all(t == t.lower() for t in terms)
