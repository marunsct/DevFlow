# Change Brief: Tasks API - due dates, a filter and a summary

## Overview
The Tasks API in this repository is in use. Add due dates to items, a filter
for done and not-done items, and a summary of a person's items. Everything the
service does today keeps working exactly as it does: the same routes, the same
answers, the same data across a restart.

## Requirements
1. **Features**:
   - An item may have a due date; a new item has none unless one is given
   - Set or clear an item's due date
   - List only your done, or only your not-done, items
   - A summary of your items: how many, how many done, how many overdue
2. **Compatibility**: every existing request answers as it does today.

## Interface
- An item is now `{"id": <integer>, "title": <string>, "done": <boolean>, "due": <"YYYY-MM-DD" or null>}`.
- `POST /items` with `{"title": ..., "due": "YYYY-MM-DD"}` (`due` optional) answers 201 with the item; a `due` that is not a real `YYYY-MM-DD` date is refused with 400 or 422, and nothing is stored.
- `PATCH /items/{id}` takes `{"done": true|false}`, `{"due": "YYYY-MM-DD" | null}`, or both, and answers 200 with the item; a bad `due` is refused with 400 or 422 and changes nothing.
- `GET /items?done=true` and `GET /items?done=false` answer 200 with only those of the signed-in person's items; `GET /items` with no filter answers all of them, as today.
- `GET /items/stats` answers 200 with `{"total": n, "done": n, "overdue": n}` for the signed-in person: overdue is not done and due before today (UTC).
- The change is made in this repository where the code is now: `start.sh` stays at its root. Every other route, answer and the `start.sh` contract (`PORT`, `DATA_DIR`, nothing else set) are as they are in the repository today. Data stored before the change keeps working: items stored without a due date have `"due": null`.

## Technical Constraints
- Python, the existing code base; data stays in SQLite under `DATA_DIR`

## Acceptance Criteria
- Due dates can be given, changed and cleared, and are refused when not a real date
- The done filter lists only the items it names
- The summary counts total, done and overdue items correctly
- Every existing behaviour of the service is unchanged
