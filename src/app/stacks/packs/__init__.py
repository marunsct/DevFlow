"""Every stack pack the harness knows, in the order `choose_pack` tries them."""

from __future__ import annotations

from app.stacks.packs.browser_javascript import PACK as BROWSER_JAVASCRIPT
from app.stacks.packs.browser_react import PACK as BROWSER_REACT
from app.stacks.packs.browser_vue import PACK as BROWSER_VUE
from app.stacks.packs.fullstack_frameworks import REACT_EXPRESS, REACT_FASTAPI, VUE_EXPRESS, VUE_FASTAPI
from app.stacks.packs.fullstack_node import PACK as FULLSTACK_NODE
from app.stacks.packs.node_http_api import PACK as NODE_HTTP_API
from app.stacks.packs.python_cli import PACK as PYTHON_CLI
from app.stacks.packs.python_http_api import PACK as PYTHON_HTTP_API
from app.stacks.packs.python_library import PACK as PYTHON_LIBRARY

ALL_PACKS = (
    BROWSER_JAVASCRIPT,
    BROWSER_REACT,
    BROWSER_VUE,
    NODE_HTTP_API,
    REACT_EXPRESS,
    VUE_EXPRESS,
    REACT_FASTAPI,
    VUE_FASTAPI,
    FULLSTACK_NODE,
    PYTHON_HTTP_API,
    PYTHON_CLI,
    PYTHON_LIBRARY,
)
