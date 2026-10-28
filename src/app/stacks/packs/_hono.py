"""What the Hono packs share."""
from __future__ import annotations

#: Errors a Hono service on Node is known to raise, by a phrase of the message, and their cause. Measured on one run:
#: `c.body('', 204)` threw "Invalid response status code 204" on every delete; the unit tests reported it, two fixes
#: did not close it, and the sprint was planned again. Four of 35 earlier products wrote that form or `c.text('', 204)`.
HONO_KNOWN_ERRORS = {
    "Invalid response status code 204": (
        "a response with status 204 carries no body, not even an empty string, and Node refuses to build one: "
        "answer it with `c.body(null, 204)`, never `c.body('', 204)` or `c.text('', 204)`."
    ),
}
