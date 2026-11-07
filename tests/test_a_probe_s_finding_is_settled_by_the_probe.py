"""A finding of the contract's own probes is settled by asking that probe again, not the criterion's tests.

Measured on one run: the emptied-field probe found `PATCH` taking an empty title and cited the criterion refusing it;
the dispatch re-measure ran that criterion's acceptance file, which tries an empty title on create only, saw it pass
and closed the finding without a fixer - three rounds running, until the product passing every locked test escalated.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import interface_contract
from app.graph import workflow

FINDING = (interface_contract.EMPTIED_FIELD_ACCEPTED + " `PATCH /items/{id}` with an empty `title` answered 200. "
           "The criteria refuse that field empty on every write (AC-5), not only where the suite tried it.")


def test_the_finding_stays_while_the_probe_still_finds_it(tmp_path, monkeypatch):
    monkeypatch.setattr(interface_contract, "emptied_field_errors", lambda root: [("check", 200)])
    assert workflow._the_defect_s_tests_pass(tmp_path, SimpleNamespace(description=FINDING)) is False


def test_it_closes_when_the_probe_no_longer_finds_it_and_is_unknown_when_it_cannot_run(tmp_path, monkeypatch):
    monkeypatch.setattr(interface_contract, "emptied_field_errors", lambda root: [])
    assert workflow._the_defect_s_tests_pass(tmp_path, SimpleNamespace(description=FINDING)) is True
    monkeypatch.setattr(interface_contract, "emptied_field_errors", lambda root: None)
    assert workflow._the_defect_s_tests_pass(tmp_path, SimpleNamespace(description=FINDING)) is None
