"""Hidden tests for the change: due dates, the done filter and the summary (brief.md's Interface)."""

import uuid
from datetime import date, timedelta

from conftest import sign_up_and_in

TODAY = date.today()


def _item(api, who, **body):
    made = api.post("/items", json={"title": f"item {uuid.uuid4().hex[:6]}", **body}, headers=who)
    assert made.status_code == 201, made.text
    return made.json()


def test_a_new_item_has_no_due_date_unless_given_one(api):
    who = sign_up_and_in(api)
    assert _item(api, who)["due"] is None
    assert _item(api, who, due="2031-04-05")["due"] == "2031-04-05"


def test_a_due_date_that_is_not_a_real_date_is_refused_and_nothing_stored(api):
    who = sign_up_and_in(api)
    before = len(api.get("/items", headers=who).json())
    for bad in ("2031-02-30", "tomorrow", "05/04/2031"):
        assert api.post("/items", json={"title": "x", "due": bad}, headers=who).status_code in (400, 422)
    assert len(api.get("/items", headers=who).json()) == before


def test_a_due_date_is_set_changed_and_cleared(api):
    who = sign_up_and_in(api)
    item = _item(api, who)
    changed = api.patch(f"/items/{item['id']}", json={"due": "2032-01-02", "done": True}, headers=who)
    assert changed.status_code == 200 and changed.json()["due"] == "2032-01-02" and changed.json()["done"] is True
    cleared = api.patch(f"/items/{item['id']}", json={"due": None}, headers=who)
    assert cleared.status_code == 200 and cleared.json()["due"] is None and cleared.json()["done"] is True
    assert api.patch(f"/items/{item['id']}", json={"due": "not-a-date"}, headers=who).status_code in (400, 422)


def test_the_done_filter_lists_only_the_items_it_names(api):
    who = sign_up_and_in(api)
    done, open_ = _item(api, who), _item(api, who)
    api.patch(f"/items/{done['id']}", json={"done": True}, headers=who)
    only_done = {i["id"] for i in api.get("/items", params={"done": "true"}, headers=who).json()}
    only_open = {i["id"] for i in api.get("/items", params={"done": "false"}, headers=who).json()}
    assert done["id"] in only_done and open_["id"] not in only_done
    assert open_["id"] in only_open and done["id"] not in only_open


def test_the_summary_counts_total_done_and_overdue(api):
    who, other = sign_up_and_in(api), sign_up_and_in(api)
    _item(api, who, due=(TODAY - timedelta(days=3)).isoformat())
    late_but_done = _item(api, who, due=(TODAY - timedelta(days=1)).isoformat())
    api.patch(f"/items/{late_but_done['id']}", json={"done": True}, headers=who)
    _item(api, who, due=(TODAY + timedelta(days=5)).isoformat())
    _item(api, who)
    _item(api, other, due=(TODAY - timedelta(days=9)).isoformat())

    stats = api.get("/items/stats", headers=who)

    assert stats.status_code == 200 and stats.json() == {"total": 4, "done": 1, "overdue": 1}
    assert api.get("/items/stats").status_code == 401
