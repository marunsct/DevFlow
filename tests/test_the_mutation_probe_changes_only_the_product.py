"""The mutation probe changes the product's code, never its tests, whatever the language calls them (found on a run).

Measured on one run (a Ruby service): the probe changed `spec/app_spec.rb` line 9 - an RSpec test file - and the
release reported that no test noticed. Its own skip list knew JavaScript's `.spec.` and a `tests/` folder, not Ruby's
`spec/` folder or `_spec.rb`; the harness's shared classifier already calls those tests.
"""
from __future__ import annotations

from app.acceptance import mutation


def _project(tmp_path):
    for relative, text in {
        "app.rb": "def ok?(a, b)\n  a || b\nend\n",
        "spec/app_spec.rb": "it 'x' do\n  expect(ok?(true, false) || true).to be true\nend\n",
        "spec/spec_helper.rb": "x = 1 if true || false\n",
        "lib/store.rb": "def keep(a)\n  a && true\nend\n",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def test_test_files_of_any_language_are_never_changed(tmp_path):
    chosen = {p.relative_to(tmp_path).as_posix() for p in mutation.source_files(_project(tmp_path))}
    assert chosen == {"app.rb", "lib/store.rb"}
