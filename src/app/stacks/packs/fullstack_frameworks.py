"""Browser interfaces in React or Vue, each served by a service in Express or FastAPI. See `_fullstack`."""

from __future__ import annotations

from app.stacks.packs._fullstack import EXPRESS, FASTAPI, REACT, VUE, fullstack_pack

REACT_EXPRESS = fullstack_pack(REACT, EXPRESS)
VUE_EXPRESS = fullstack_pack(VUE, EXPRESS)
REACT_FASTAPI = fullstack_pack(REACT, FASTAPI)
VUE_FASTAPI = fullstack_pack(VUE, FASTAPI)
