"""Every stack pack the harness knows, in the order `choose_pack` tries them."""

from __future__ import annotations

from app.stacks.packs.browser_javascript import PACK as BROWSER_JAVASCRIPT
from app.stacks.packs.browser_react import PACK as BROWSER_REACT
from app.stacks.packs.browser_svelte import PACK as BROWSER_SVELTE
from app.stacks.packs.browser_vue import PACK as BROWSER_VUE
from app.stacks.packs.csharp_aspnet_api import PACK as CSHARP_ASPNET_API
from app.stacks.packs.fullstack_frameworks import REACT_EXPRESS, REACT_FASTAPI, VUE_EXPRESS, VUE_FASTAPI
from app.stacks.packs.fullstack_django import PACK as FULLSTACK_DJANGO
from app.stacks.packs.fullstack_next import PACK as FULLSTACK_NEXT
from app.stacks.packs.fullstack_node import PACK as FULLSTACK_NODE
from app.stacks.packs.go_gin_api import PACK as GO_GIN_API
from app.stacks.packs.go_http_api import PACK as GO_HTTP_API
from app.stacks.packs.java_spring_api import PACK as JAVA_SPRING_API
from app.stacks.packs.node_http_api import PACK as NODE_HTTP_API
from app.stacks.packs.node_nest_api import PACK as NODE_NEST_API
from app.stacks.packs.php_laravel_api import PACK as PHP_LARAVEL_API
from app.stacks.packs.php_slim_api import PACK as PHP_SLIM_API
from app.stacks.packs.python_cli import PACK as PYTHON_CLI
from app.stacks.packs.python_flask_api import PACK as PYTHON_FLASK_API
from app.stacks.packs.python_http_api import PACK as PYTHON_HTTP_API
from app.stacks.packs.python_library import PACK as PYTHON_LIBRARY
from app.stacks.packs.ruby_rails_api import PACK as RUBY_RAILS_API
from app.stacks.packs.ruby_sinatra_api import PACK as RUBY_SINATRA_API
from app.stacks.packs.rust_axum_api import PACK as RUST_AXUM_API

ALL_PACKS = (
    BROWSER_JAVASCRIPT,
    BROWSER_REACT,
    BROWSER_VUE,
    BROWSER_SVELTE,
    NODE_HTTP_API,
    NODE_NEST_API,
    REACT_EXPRESS,
    VUE_EXPRESS,
    REACT_FASTAPI,
    VUE_FASTAPI,
    FULLSTACK_NEXT,
    FULLSTACK_DJANGO,
    FULLSTACK_NODE,
    PYTHON_HTTP_API,
    PYTHON_FLASK_API,
    PYTHON_CLI,
    PYTHON_LIBRARY,
    GO_HTTP_API,
    GO_GIN_API,
    JAVA_SPRING_API,
    CSHARP_ASPNET_API,
    RUST_AXUM_API,
    RUBY_SINATRA_API,
    RUBY_RAILS_API,
    PHP_SLIM_API,
    PHP_LARAVEL_API,
)
