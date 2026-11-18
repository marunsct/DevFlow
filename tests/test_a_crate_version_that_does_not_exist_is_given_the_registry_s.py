"""A Rust manifest pinning a crate version the registry lacks is told the registry's current release.

Measured on a Rust run: `rusqlite = "0.37.4"` had no such version; cargo said so, the install note gave no registry line,
and the fixer's next guess, 0.36, also failed to resolve.
"""
from __future__ import annotations

from app.stacks import contract, pack_named

CARGO_SAID = ('Updating crates.io index\nerror: failed to select a version for the requirement `rusqlite = "^0.37.4"`\n'
              "candidate versions found which didn't match: 0.43.0, 0.42.0, 0.41.1, ...\n")


def test_the_install_note_names_the_registry_s_current_release(tmp_path, monkeypatch):
    pack = pack_named("rust-axum-api")
    contract.write(tmp_path, pack, "notes-api", "Notes", None, scaffolded=True)
    (tmp_path / "notes-api").mkdir(exist_ok=True)
    (tmp_path / "notes-api" / "Cargo.toml").write_text('[dependencies]\nrusqlite = "0.37.4"\n')
    monkeypatch.setattr("app.tools.package_registry.enabled", lambda: True)
    asked = []
    monkeypatch.setattr("app.tools.package_registry.look_up",  # the registry is the edge
                        lambda ecosystem, name, **kw: asked.append((ecosystem, name)) or {"version": "0.43.0"})

    def the_installer(argv, category, project):  # the toolchain is the edge
        return {"returncode": 101, "stdout": "", "stderr": CARGO_SAID}

    notes = contract.install_if_the_manifests_changed(tmp_path, runner=the_installer)

    assert asked == [("crates", "rusqlite")]
    assert notes and "The registry's current release of `rusqlite` is 0.43.0" in notes[0]
