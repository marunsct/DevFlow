"""A brief's line limit counts what the team writes, not the design-token stylesheet the pack started it with (PQ.6).

Measured on one stored product: a milestone review asked to delete the pack's token file as dead code to get under a
500-line limit, and the page lost its dark scheme and focus ring. The tokens and base element styles are the harness's
starting point; a value the product changed and every rule it added still count.
"""
from __future__ import annotations

from pathlib import Path

from app.analysis.integration_checks import budget_note_for_a_write
from app.stacks import contract, pack_named


def _a_product(root: Path, code_lines: int, added_styles: str = "", *, scaffolded: bool = True) -> None:
    pack = pack_named("browser-javascript")
    project = root / "notes"
    (project / "src").mkdir(parents=True)
    (project / "index.html").write_text(pack.files["index.html"].replace("{{title}}", "Notes"))
    (project / "styles.css").write_text((pack.files["styles.css"] if scaffolded else "") + added_styles)
    (project / "src" / "main.js").write_text("".join(f"export const value{n} = {n};\n" for n in range(code_lines)))
    contract.write(root, pack, "notes", "Notes")
    (root / "docs").mkdir()
    (root / "docs" / "brief.md").write_text("## Technical Constraints\n- Maximum 500 lines of code\n")


def test_the_scaffold_s_stylesheet_is_not_counted_against_the_limit(tmp_path):
    _a_product(tmp_path, code_lines=480)

    assert budget_note_for_a_write(tmp_path, "notes/src/main.js") == ""


def test_rules_the_product_adds_to_it_still_count(tmp_path):
    added = "".join(f".row-{n} {{ padding: var(--space-2); }}\n" for n in range(30))
    _a_product(tmp_path / "on-the-scaffold", code_lines=480, added_styles=added)
    _a_product(tmp_path / "its-own-only", code_lines=480, added_styles=added, scaffolded=False)

    note = budget_note_for_a_write(tmp_path / "on-the-scaffold", "notes/src/main.js")

    assert "now holds" in note
    assert note == budget_note_for_a_write(tmp_path / "its-own-only", "notes/src/main.js")


def test_a_product_over_the_limit_on_its_own_code_is_still_told(tmp_path):
    _a_product(tmp_path, code_lines=520)

    assert "now holds" in budget_note_for_a_write(tmp_path, "notes/src/main.js")
