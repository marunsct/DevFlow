from __future__ import annotations

from types import SimpleNamespace
from langchain_core.messages import HumanMessage

from app.agents import project_memory
from app.tools.seen_content import has_seen_this_version


def test_project_memory_records_held_files_in_seen_content(tmp_path):
    """Files handed to a stage in project memory or intercepted by it must be marked as seen
    in seen_content so subsequent writes do not get falsely refused as 'unread'.
    """
    app_file = tmp_path / "notes-api" / "src" / "store.ts"
    app_file.parent.mkdir(parents=True)
    content = "export const store = 1;\n"
    app_file.write_text(content)

    middleware = project_memory.build_project_memory_middleware(str(tmp_path))

    class Request(SimpleNamespace):
        def override(self, **changes):
            return Request(**{**self.__dict__, **changes})

    # Initially not seen
    assert not has_seen_this_version("notes-api/src/store.ts", content)

    # When model call happens, project memory hands the file to the model
    middleware.wrap_model_call(
        Request(messages=[HumanMessage(content="Build it")], model=None),
        lambda r: None,
    )

    # Now the stage has received this file content in its prompt, so it has seen it!
    assert has_seen_this_version("notes-api/src/store.ts", content), (
        "Project memory handed the file in context, but seen_content did not record it as seen"
    )

