"""A fix whose product change broke acceptance tests keeps its repair of the unit tests.

Measured live: a fix for "the unit tests fail" rewrote the unit test file - 24
tests passed that did not - and changed one router, which broke 13 sign-in
acceptance tests. The whole fix was reverted, the test repair with it. The
acceptance suite runs the product, so the unit test file cannot be what broke it.
"""
from __future__ import annotations

import subprocess

from app import ci
from app.graph import engineering

ROUTER = "shop/shop_pkg/routers/items.py"
UNIT_TEST = "shop/tests/test_items.py"


def _git(root, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True,
                   capture_output=True)


def _workspace(tmp_path):
    for path, text in ((ROUTER, "def items(user=Depends(signed_in)):\n    return []\n"),
                       (UNIT_TEST, "def test_items(\n    await client.get('/items')\n")):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "before the fix")
    return tmp_path, ci.head(tmp_path)


def _measured(root, label):
    signed_in = "Depends(signed_in)" in (root / ROUTER).read_text()
    repaired = "async def test_items" in (root / UNIT_TEST).read_text()
    return ci.Snapshot(
        label=label, unit={"pytest › tests.test_items": "passed" if repaired else "failed"}, unit_ran=True,
        acceptance={"auth.spec.js › [AC-8] a protected route refuses a stranger": "passed" if signed_in else "failed"},
        acceptance_ran=True,
    )


def test_the_test_repair_is_kept_and_the_product_change_put_back(tmp_path, monkeypatch):
    root, base = _workspace(tmp_path)
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "take", lambda r, label: _measured(root, label))
    before = _measured(root, "before")
    saved = {}
    monkeypatch.setattr(ci, "save", lambda r, snapshot, accepted=False: saved.update(latest=snapshot))
    monkeypatch.setattr(ci, "load", lambda r, which: saved.get("latest") or before)
    # The fix: the unit test repaired, and the route's sign-in taken away.
    (root / UNIT_TEST).write_text("async def test_items(client):\n    await client.get('/items')\n")
    (root / ROUTER).write_text("def items():\n    return []\n")

    broke = engineering.after_a_fix(str(root), base, "defect_fix_2_2", "The unit tests fail")

    assert broke == []
    assert "async def test_items" in (root / UNIT_TEST).read_text()
    assert "Depends(signed_in)" in (root / ROUTER).read_text()
    assert saved["latest"].label == "after defect_fix_2_2", "the settlement reads this measurement"


def test_a_broken_unit_test_still_reverts_the_whole_fix(tmp_path, monkeypatch):
    """A unit test file can break unit tests, so nothing is kept on that evidence."""
    root, base = _workspace(tmp_path)
    (root / UNIT_TEST).write_text("async def test_items(client):\n    await client.get('/items')\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the unit tests pass")
    base = ci.head(root)
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "take", lambda r, label: _measured(root, label))
    before = _measured(root, "before")
    monkeypatch.setattr(ci, "load", lambda r, which: before)
    (root / UNIT_TEST).write_text("def test_items(\n")

    broke = engineering.after_a_fix(str(root), base, "defect_fix_2_3", "x")

    assert broke == ["unit: pytest › tests.test_items"]
    assert "async def test_items" in (root / UNIT_TEST).read_text(), "reverted to before the fix"


def test_a_split_that_breaks_too_leaves_the_fix_as_it_was_written(tmp_path, monkeypatch):
    """Found in building LF.1271: when keeping the tests alone broke the same test, the product change stayed put back,
    and a fix then kept on its net gain was committed without the change that was measured."""
    monkeypatch.setenv("KEEP_NET_GAINS", "on")
    root, base = _workspace(tmp_path)

    def measured(r, label):
        router, test = (root / ROUTER).read_text(), (root / UNIT_TEST).read_text()
        as_before = "Depends(signed_in)" in router and test.startswith("def test_items(")
        return ci.Snapshot(label=label, unit={"pytest › tests.test_items": "passed"}, unit_ran=True, acceptance_ran=True,
                           acceptance={"a.spec.js › [AC-8] refuses a stranger": "passed" if as_before else "failed",
                                       **{f"a.spec.js › [AC-9] lists {n}": "passed" if "paged" in router else "failed"
                                          for n in range(4)}})

    before = measured(root, "before")
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "take", measured)
    monkeypatch.setattr(ci, "load", lambda r, which: before)
    monkeypatch.setattr(ci, "save", lambda r, snapshot, accepted=False: None)
    (root / UNIT_TEST).write_text("async def test_items(client):\n    await client.get('/items')\n")
    (root / ROUTER).write_text("def items(paged=True):\n    return []\n")

    broke = engineering.after_a_fix(str(root), base, "defect_fix_2_4", "lists")

    assert broke == [], "kept on its net gain"
    assert "paged" in (root / ROUTER).read_text(), "with the product change that gained the four tests"
