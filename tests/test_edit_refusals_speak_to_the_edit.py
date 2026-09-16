r"""An edit refused for a broken file is answered in the edit's own terms.

Run 8d28ee3f, `specialist_ui_ux_0`, made six `edit_artifact` calls on
package.json. Every one was refused with "Refusing to *write* ... Send the
file again as complete, valid JSON" - a verb naming a tool it had not called,
and an instruction it could not follow through the one it had. It switched to
`write_artifact` on the seventh, which is what the message had been describing
from the start.

Two of those six also sent `\n` as the two characters `\` and `n` in
`replace`. The forgiving matcher already resolves that spelling on the `find`
side; the replacement went through literally and broke the file.
"""

import json

import pytest

from app.tools.repository import (
    RepositoryToolError,
    _refusal_for,
    edit_approved_artifact,
    read_text_file,
)

MANIFEST = (
    '{\n  "name": "todo",\n  "main": "app.js",\n'
    '  "scripts": {\n    "test": "node --test"\n  }\n}\n'
)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "package.json").write_text(MANIFEST, encoding="utf-8")
    (tmp_path / "app.js").write_text("export function a() {\n  return 1;\n}\n", encoding="utf-8")
    return tmp_path


def test_the_verb_names_the_tool_that_was_called():
    assert _refusal_for("package.json", "It is broken.", editing=True).startswith(
        "Refusing to change"
    )
    assert _refusal_for("package.json", "It is broken.").startswith("Refusing to write")


def test_an_edit_is_not_told_to_send_the_whole_file():
    message = _refusal_for(
        "package.json",
        "This is not valid JSON at line 9. Send the file again as complete, valid JSON.",
        editing=True,
    )
    assert "Send the file again" not in message
    assert "Fix `replace` and send the edit again." in message


def test_a_write_keeps_the_instruction_that_suits_it():
    message = _refusal_for(
        "package.json",
        "This is not valid JSON at line 9. Send the file again as complete, valid JSON.",
    )
    assert "Send the file again as complete, valid JSON." in message
    assert "Nothing was written." in message


def test_an_edit_that_breaks_json_says_change_not_write(project):
    read_text_file(project, "package.json")
    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(project, "package.json", '"main": "app.js",', '"main" "app.js"')
    assert "Refusing to change" in str(caught.value)


def test_a_replacement_with_escaped_newlines_is_rescued(project):
    r"""`\n` as two characters, which is how the model spelled it twice."""
    read_text_file(project, "package.json")

    result = edit_approved_artifact(
        project,
        "package.json",
        '"scripts": {',
        '"type": "module",\\n  "scripts": {',
    )

    assert result["status"] == "edited"
    written = json.loads((project / "package.json").read_text(encoding="utf-8"))
    assert written["type"] == "module"
    assert written["scripts"] == {"test": "node --test"}


def test_the_rescue_only_applies_when_it_makes_the_file_valid(project):
    """An edit that is broken for some other reason is still refused."""
    read_text_file(project, "package.json")
    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(
            project, "package.json", '"scripts": {', '"type" "module",\\n  "scripts": {'
        )
    assert (project / "package.json").read_text(encoding="utf-8") == MANIFEST


def test_a_literal_backslash_n_in_valid_code_is_left_alone(project):
    r"""`console.log("a\nb")` is correct JavaScript and must survive intact."""
    read_text_file(project, "app.js")

    edit_approved_artifact(
        project, "app.js", "  return 1;", '  console.log("a\\nb");\n  return 1;'
    )

    written = (project / "app.js").read_text(encoding="utf-8")
    assert r'console.log("a\nb")' in written


def test_escapes_elsewhere_in_the_file_are_not_touched(project):
    r"""Only the span the edit changed is resolved."""
    (project / "app.js").write_text(
        'export function a() {\n  const s = "x\\ny";\n  return 1;\n}\n', encoding="utf-8"
    )
    read_text_file(project, "app.js")

    edit_approved_artifact(project, "app.js", "  return 1;", "  return 2;")

    assert r'const s = "x\ny";' in (project / "app.js").read_text(encoding="utf-8")
