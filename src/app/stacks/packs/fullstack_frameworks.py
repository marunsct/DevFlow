"""Browser interfaces in React, Vue or plain HTML and JavaScript, each served by a service in Express or FastAPI. See `_fullstack`."""

from __future__ import annotations

from app.stacks.packs._fullstack import EXPRESS, FASTAPI, PLAIN, REACT, VUE, fullstack_pack

REACT_EXPRESS = fullstack_pack(REACT, EXPRESS)
VUE_EXPRESS = fullstack_pack(VUE, EXPRESS)
REACT_FASTAPI = fullstack_pack(REACT, FASTAPI)
VUE_FASTAPI = fullstack_pack(VUE, FASTAPI)
PAGE_FASTAPI = fullstack_pack(PLAIN, FASTAPI)
