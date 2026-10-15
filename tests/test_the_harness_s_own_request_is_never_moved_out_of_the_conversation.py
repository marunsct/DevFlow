"""The harness's own request to a stage is never moved out of the conversation into a file.

Every architect visit on three runs had its opening request moved to
`conversation_history/<uuid>.md` and read it back window by window.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.agents.role_agent import _workspace_filesystem_middleware


def test_a_large_request_stays_in_the_conversation(tmp_path):
    middleware = _workspace_filesystem_middleware(str(tmp_path))

    assert middleware._check_eviction_needed([HumanMessage(content="x" * 1_000_000)]) == (False, False)


def test_a_large_tool_result_is_still_kept_out(tmp_path):
    middleware = _workspace_filesystem_middleware(str(tmp_path))

    assert middleware._tool_token_limit_before_evict
