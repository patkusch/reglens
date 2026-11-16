"""The agent's flow and the write-back, with the DataHub server and the keyboard replaced by stand-ins."""
import asyncio
import json
from types import SimpleNamespace
from unittest import mock

import pytest

from reglens.agent import reglens_agent as agent
from reglens.agent import writeback
from reglens.seed.regulations import REGULATIONS

REG = "RCS-2026"


def payload(targets=("urn:li:dataset:a", "urn:li:dashboard:b")):
    return {"glossary_term": "RegLens.ActNow", "description": "Decision: act now.", "targets": list(targets)}


class FakeEntity:
    def __init__(self, urn, *, fail_description=False, fail_editable=False, fail_term=False):
        self.urn = SimpleNamespace(entity_type=urn.split(":")[2])
        self.fail = (fail_description, fail_editable, fail_term)
        self.description = self.editable = None
        self.terms = []

    def set_description(self, text):
        if self.fail[0]:
            raise NotImplementedError("no plain description on this type")
        self.description = text

    def set_editable_description(self, text):
        if self.fail[1]:
            raise RuntimeError("no editable description either")
        self.editable = text

    def add_term(self, term):
        if self.fail[2]:
            raise ValueError("term rejected")
        self.terms.append(term)


class FakeClient:
    def __init__(self, entities, fail_update=()):
        self.store = entities
        self.updated = []
        self.fail_update = set(fail_update)
        self.entities = SimpleNamespace(get=self._get, update=self._update)

    def _get(self, urn):
        if urn not in self.store:
            raise KeyError(f"no such entity {urn}")
        return self.store[urn]

    def _update(self, entity):
        urn = next(u for u, e in self.store.items() if e is entity)
        if urn in self.fail_update:
            raise ConnectionError("server unreachable")
        self.updated.append(urn)


def make(*urns, **kw):
    return FakeClient({u: FakeEntity(u, **kw) for u in urns})


def test_each_target_gets_the_description_and_the_term_and_is_saved(capsys):
    client = make("urn:li:dataset:a", "urn:li:dashboard:b")
    done = writeback.write_assessment_via_sdk(payload(), client=client)
    assert done == ["urn:li:dataset:a", "urn:li:dashboard:b"]
    assert client.updated == done
    for entity in client.store.values():
        assert entity.description == "Decision: act now."
        assert len(entity.terms) == 1
    out = capsys.readouterr().out
    assert "wrote assessment -> dataset" in out and "wrote assessment -> dashboard" in out


def test_an_entity_type_with_only_an_editable_description_gets_that_instead(capsys):
    client = make("urn:li:mlModel:m", fail_description=True)
    assert writeback.write_assessment_via_sdk(payload(["urn:li:mlModel:m"]), client=client) == ["urn:li:mlModel:m"]
    entity = client.store["urn:li:mlModel:m"]
    assert entity.description is None and entity.editable == "Decision: act now."


def test_a_description_that_cannot_be_set_either_way_is_a_warning_and_the_rest_still_goes_through(capsys):
    client = make("urn:li:dataset:a", fail_description=True, fail_editable=True)
    assert writeback.write_assessment_via_sdk(payload(["urn:li:dataset:a"]), client=client) == ["urn:li:dataset:a"]
    out = capsys.readouterr().out
    assert "[warn] description on dataset urn:li:dataset:a: no editable description either" in out
    assert len(client.store["urn:li:dataset:a"].terms) == 1


def test_a_term_that_cannot_be_added_is_a_warning_not_a_failure(capsys):
    client = make("urn:li:dataset:a", fail_term=True)
    assert writeback.write_assessment_via_sdk(payload(["urn:li:dataset:a"]), client=client) == ["urn:li:dataset:a"]
    assert "[warn] glossary term on dataset urn:li:dataset:a: term rejected" in capsys.readouterr().out


def test_an_asset_that_cannot_be_read_or_saved_is_left_out_of_the_result_and_the_others_continue(capsys):
    client = FakeClient({"urn:li:dataset:ok": FakeEntity("urn:li:dataset:ok"), "urn:li:dataset:down": FakeEntity("urn:li:dataset:down")}, fail_update=["urn:li:dataset:down"])
    targets = ["urn:li:dataset:missing", "urn:li:dataset:down", "urn:li:dataset:ok"]
    assert writeback.write_assessment_via_sdk(payload(targets), client=client) == ["urn:li:dataset:ok"]
    out = capsys.readouterr().out
    assert "[warn] could not update urn:li:dataset:missing: " in out
    assert "[warn] could not update urn:li:dataset:down: server unreachable" in out


def test_no_targets_means_nothing_written():
    client = make()
    assert writeback.write_assessment_via_sdk(payload([]), client=client) == []
    assert client.updated == []


def test_the_term_is_attached_under_the_name_in_the_payload():
    client = make("urn:li:dataset:a")
    writeback.write_assessment_via_sdk(payload(["urn:li:dataset:a"]), client=client)
    assert "RegLens.ActNow" in str(client.store["urn:li:dataset:a"].terms[0])


def run(**kw):
    args = dict(use_mcp=False, dry_run=True, auto_approve=True)
    args.update(kw)
    return asyncio.run(agent.run(REG, **args))


def test_the_human_gate_accepts_y_and_yes_in_any_case_and_nothing_else(capsys):
    assessment = agent.build_assessment(REG, agent.discover_impact_deterministic())
    for typed, expected in [("y", True), ("YES", True), (" Yes ", True), ("", False), ("n", False), ("maybe", False), ("yep", False)]:
        with mock.patch("builtins.input", return_value=typed):
            assert agent.human_gate(assessment) is expected, repr(typed)
    assert "Approve and write this assessment back to DataHub? [y/N]" not in capsys.readouterr().out, "the prompt goes to input(), not the screen"


def test_a_dry_run_shows_what_it_would_write_and_writes_nothing(capsys):
    with mock.patch.object(writeback, "write_assessment_via_sdk") as write:
        run(dry_run=True)
    write.assert_not_called()
    out = capsys.readouterr().out
    assert f"RegLens :: {REG} — {REGULATIONS[REG].title}" in out
    assert f"Discovered {len(agent.discover_impact_deterministic())} affected assets downstream of {agent.ANCHOR}." in out
    assert "[dry-run] Would write back:" in out
    assert "term: " in out and "to " in out and " assets" in out


def test_when_the_person_says_no_nothing_is_written_and_the_assessment_is_printed_as_json(capsys):
    with mock.patch("builtins.input", return_value="n"), mock.patch.object(writeback, "write_assessment_via_sdk") as write:
        run(auto_approve=False, dry_run=False)
    write.assert_not_called()
    out = capsys.readouterr().out
    assert "Not approved — nothing written. (Assessment JSON below.)" in out
    data = json.loads(out[out.index("Not approved"):].split("\n", 1)[1])
    assert data["regulation_id"] == REG


def test_when_the_person_says_yes_the_assessment_is_written_and_the_count_is_reported(capsys):
    with mock.patch("builtins.input", return_value="y"), \
         mock.patch.object(writeback, "write_assessment_via_sdk", return_value=["u1", "u2", "u3"]) as write:
        run(auto_approve=False, dry_run=False)
    sent = write.call_args.args[0]
    assert sent["targets"] and sent["glossary_term"] and sent["description"]
    out = capsys.readouterr().out
    assert "Writing assessment back into DataHub..." in out
    assert "Done. 3 assets now carry the RegLens assessment." in out
    assert f"look at {agent.ANCHOR}" in out


def test_auto_approve_skips_the_question_entirely(capsys):
    with mock.patch("builtins.input", side_effect=AssertionError("must not ask")):
        run(auto_approve=True, dry_run=True)


def test_the_assessment_dates_itself_and_rates_impact_by_how_many_assets_are_hit():
    assets = agent.discover_impact_deterministic()
    a = agent.build_assessment(REG, assets)
    assert a.assessment_date == __import__("datetime").date.today().isoformat()
    assert a.impact == ("HIGH" if len(assets) >= 6 else "MEDIUM")
    few = agent.build_assessment(REG, assets[:2])
    assert few.impact == "MEDIUM"
    many = agent.build_assessment(REG, (assets * 3)[:6])
    assert many.impact == "HIGH"


@pytest.mark.parametrize("argv,expected", [
    ([], dict(use_mcp=True, dry_run=False, auto_approve=False)),
    (["--no-mcp", "--dry-run", "--yes"], dict(use_mcp=False, dry_run=True, auto_approve=True)),
    (["--no-mcp"], dict(use_mcp=False, dry_run=False, auto_approve=False)),
])
def test_the_command_line_flags_map_onto_the_run_options(argv, expected):
    async def fake_run(reg, **kw):
        fake_run.seen = (reg, kw)

    with mock.patch("sys.argv", ["reglens", *argv]), mock.patch.object(agent, "run", fake_run):
        agent.main()
    assert fake_run.seen == (REG, expected)


def test_an_unknown_regulation_is_refused_by_the_parser(capsys):
    with mock.patch("sys.argv", ["reglens", "--reg", "NOPE"]), pytest.raises(SystemExit) as e:
        agent.main()
    assert e.value.code == 2
