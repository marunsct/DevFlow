"""A specification part that comes back without its interface contract is asked for that section once more.

Measured: 5 of 206 specifications shipped "Not specified" as their interface contract; the release probes then had no
line to check, and one release's README said nowhere how to run the product, though its commands stood elsewhere.
"""
import json
from types import SimpleNamespace

from pydantic import BaseModel

from app.graph import specification_parts


class Spec(BaseModel):
    file_plan: list[str] = []
    acceptance_criteria: list[str] = []
    interface_contract: list[str] = []


class _Model:
    def __init__(self, give_it_at=2):
        self.asked, self.give_it_at = [], give_it_at

    def invoke(self, messages, **kwargs):
        wanted = messages[-1].content.split("Its keys are exactly:")[-1]
        names = [n for n in ("acceptance_criteria", "interface_contract") if n in wanted]
        self.asked.append(names)
        body = {n: ["- AC-1 command tool <file> -> three lines"] for n in names}
        if len(self.asked) < self.give_it_at:
            body.pop("interface_contract", None)
        return SimpleNamespace(content=json.dumps(body))


def _setup(monkeypatch, naming="off"):
    monkeypatch.setenv("NAMING_STANDARD", naming)
    monkeypatch.setattr(specification_parts, "PARTS", (("acceptance_criteria", "interface_contract"),))
    monkeypatch.setattr("app.agents.thinking.without_reasoning", lambda model: model)


def test_an_empty_contract_is_asked_for_again_whatever_the_naming_switch(monkeypatch):
    for naming in ("off", "on"):
        _setup(monkeypatch, naming)
        model = _Model()
        written = specification_parts.with_the_parts_written(Spec(), model, "")
        assert written.interface_contract and written.acceptance_criteria
        assert model.asked == [["acceptance_criteria", "interface_contract"], ["interface_contract"]]


def test_a_contract_given_the_first_time_is_asked_once(monkeypatch):
    _setup(monkeypatch)
    model = _Model(give_it_at=1)
    specification_parts.with_the_parts_written(Spec(), model, "")
    assert len(model.asked) == 1
