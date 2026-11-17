"""A manifest entry the pack's own test command needs is put back when a stage drops it (found on a run).

Measured on one run (a C# service): a work order rewrote the unit test project and dropped `JunitXml.TestLogger`; the
pack's unit command asks for that logger, so every unit run failed with "Could not find a test logger ... 'junit'"
and no test ran - fix after fix. The harness put back its kept files, not a single entry its command needs in a
manifest the builders own. Ruby's Gemfile (`rspec_junit_formatter`) and a Node manifest's `jest-junit` (named by the
kept unit script) carry the same need.
"""
from __future__ import annotations

import json

from app.stacks import contract, pack_named


def _scaffolded(tmp_path, name):
    pack = pack_named(name)
    contract.write(tmp_path, pack, "svc", "Svc", None, scaffolded=True)
    root = tmp_path / "svc"
    for relative, text in pack.render("svc", "Svc", None).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return pack, root


def test_the_csharp_test_logger_package_is_put_back(tmp_path):
    _, root = _scaffolded(tmp_path, "csharp-aspnet-api")
    project = root / "tests/UnitTests/UnitTests.csproj"
    stripped = "\n".join(l for l in project.read_text().splitlines() if "JunitXml.TestLogger" not in l)
    project.write_text(stripped.replace('Include="xunit" Version="2.9.3"', 'Include="xunit" Version="2.6.6"'))
    repairs = contract.enforce(tmp_path)
    text = project.read_text()
    assert 'Include="JunitXml.TestLogger"' in text and 'Include="xunit" Version="2.6.6"' in text
    assert any("JunitXml.TestLogger" in line for line in repairs)
    assert contract.enforce(tmp_path) == [] or not any("JunitXml" in r for r in contract.enforce(tmp_path))


def test_the_ruby_junit_formatter_gem_is_put_back(tmp_path):
    _, root = _scaffolded(tmp_path, "ruby-sinatra-api")
    gemfile = root / "Gemfile"
    gemfile.write_text('source "https://rubygems.org"\n\ngem "sinatra", "~> 4.1"\n\ngroup :test do\n  gem "rspec", "~> 3.13"\nend\n')
    contract.enforce(tmp_path)
    assert "rspec_junit_formatter" in gemfile.read_text() and 'gem "sinatra"' in gemfile.read_text()


def test_a_node_reporter_the_kept_unit_script_names_is_put_back(tmp_path):
    _, root = _scaffolded(tmp_path, "node-hono-api")
    manifest = root / "package.json"
    data = json.loads(manifest.read_text())
    data["devDependencies"].pop("jest-junit")
    data["dependencies"] = {**data.get("dependencies", {}), "left-pad": "^1.3.0"}
    manifest.write_text(json.dumps(data))
    contract.enforce(tmp_path)
    after = json.loads(manifest.read_text())
    assert "jest-junit" in after.get("devDependencies", {}) and after["dependencies"].get("left-pad") == "^1.3.0"


def test_the_ruby_start_command_s_rackup_gem_is_put_back_outside_the_test_group(tmp_path):
    """Measured on one run: a work order rewrote the Gemfile without `rackup`, which the start command runs."""
    _, root = _scaffolded(tmp_path, "ruby-sinatra-api")
    gemfile = root / "Gemfile"
    gemfile.write_text('source "https://rubygems.org"\n\ngem "sinatra", "~> 4.1"\ngem "puma", "~> 6.5"\n\n'
                       'group :test do\n  gem "rspec", "~> 3.13"\n  gem "rspec_junit_formatter", "~> 0.6"\nend\n')

    contract.enforce(tmp_path)

    text = gemfile.read_text()
    assert 'gem "rackup"' in text and text.index('gem "rackup"') < text.index("group :test")
