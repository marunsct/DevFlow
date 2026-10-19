"""Every node of the workflow graph has its words on the run page (plan BG.11).

The page names a stage by `STAGE_COPY` in `langchain-ui/src/lib/activity.ts`,
and a name it did not know fell back to the identifier in title case: a run
page's heading read "Defect Fix 2 12", and 21 of the graph's 42 nodes had no
words at all. A node added to the graph without its words now fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Nodes that are never a stage a person sees named.
NEVER_SHOWN: set[str] = set()


def _graph_nodes() -> set[str]:
    source = (ROOT / "src" / "app" / "graph" / "workflow.py").read_text()
    return set(re.findall(r'add_node\(\s*"([a-z_]+)"', source))


def _copy_keys() -> set[str]:
    source = (ROOT / "langchain-ui" / "src" / "lib" / "activity.ts").read_text()
    table = source[source.index("const STAGE_COPY"):source.index("/** Stage names a run makes as it goes")]
    return set(re.findall(r"^  ([a-z_]+): \{", table, re.M))


def test_the_graph_is_read():
    assert {"principal_architect", "defect_remediation", "release"} <= _graph_nodes()


def test_every_node_has_its_words():
    missing = sorted(_graph_nodes() - _copy_keys() - NEVER_SHOWN)
    assert not missing, f"add these to STAGE_COPY in langchain-ui/src/lib/activity.ts: {missing}"
