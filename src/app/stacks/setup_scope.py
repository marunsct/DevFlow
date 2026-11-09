"""`SETUP_SCOPE_GUARD`: a layered setup stage writes only what it is asked for, not the product (docs/measuring.md M6).

Off in code; measured with two runs per family on and off before it is kept. See
`app.tools.repository._beyond_the_setup_s_files` for the rule and why.
"""
from __future__ import annotations

from app.switches import is_on

ON_BY_DEFAULT = False
#: What the admin page says this switch does.
explanation = ("A setup stage built on its language's runner layer writes only the framework files it was asked for, "
               "its declaration, smoke tests, manifests and test configuration; a write of the product's own code is "
               "refused and left to the builders. Measured once: a setup stage wrote the whole product before the "
               "design's builders ran, and it shipped broken.")


def enabled() -> bool:
    return is_on("SETUP_SCOPE_GUARD", ON_BY_DEFAULT)


__all__ = ["ON_BY_DEFAULT", "enabled", "explanation"]
