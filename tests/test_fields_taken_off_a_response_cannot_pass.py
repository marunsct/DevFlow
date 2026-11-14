"""A test that takes fields straight off a response, not its body, cannot pass: the response has no such field.

Measured on one run: four locked tests posted a note, read `id` off the response (`const { id } = await
request.post(...)`), asked for `/notes/undefined` and got 404; three fixes of a right product were reverted.
"""
import re
from types import SimpleNamespace

from app.acceptance import suite
from app.stacks.packs import _javascript as js

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
OFF = re.compile(js.FIELDS_OFF_A_RESPONSE)


def test_fields_off_a_response_are_found():
    assert OFF.search("const { id } = await request.post('/notes', { data: {} });")
    assert OFF.search("const { id: id2 } = await page.request.get(`/notes/${x}`);")
    assert OFF.search("let { status } = await fetch('/api/notes');")


def test_fields_off_its_body_or_a_helper_are_not():
    for text in ("const { id } = await (await request.post('/notes')).json();",
                 "const { id } = await response.json();",
                 "const { id } = await createNote(request, 'x');",
                 "const response = await request.post('/notes');"):
        assert not OFF.search(text), text


def test_a_failing_test_with_one_is_the_test_s_own_and_says_why(tmp_path):
    from app.stacks import contract, pack_named

    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "crud.spec.js").write_text(
        "test('[AC-3] fetch one', async ({ request }) => {\n"
        "  const { id } = await request.post('/notes', { data: { title: 'x' } });\n"
        "  expect((await request.get(`/notes/${id}`)).status()).toBe(200);\n});\n")
    result = SimpleNamespace(ran=True, output="", report=SimpleNamespace(found=True, tests=[
        SimpleNamespace(name="[AC-3] fetch one", outcome="failed", message="Expected: 200 Received: 404")]))
    [found] = suite.tests_that_broke_themselves(tmp_path, result)
    assert "takes fields straight off the response" in found and not BANNED.search(js.TEST_SOURCE_BUG_WHY[js.FIELDS_OFF_A_RESPONSE])
