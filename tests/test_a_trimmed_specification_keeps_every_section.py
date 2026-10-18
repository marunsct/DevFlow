"""A specification fitted to a budget keeps every section in part, not just its head (Initiative O.1).

Cut to its head, a 106,000-character specification lost its last 31,000
characters whole on each judgement stage that carried it.
"""

from __future__ import annotations

from app.agents.text_budget import excerpt


def _spec() -> str:
    parts = ["# Technical specification", "Preamble."]
    for n in range(1, 11):
        parts.append(f"## Section {n}")
        parts.extend(f"line {i} of section {n}" for i in range(400 if n % 3 == 0 else 20))
    parts.append("## Acceptance criteria")
    parts.append("FINAL-SECTION-MARKER: AC-1 the list shows every note")
    return "\n".join(parts)


def test_the_last_section_survives_the_trim() -> None:
    text = _spec()
    budget = len(text) // 3

    fitted = excerpt(text, budget, what="technical specification")

    assert "FINAL-SECTION-MARKER" in fitted
    assert all(f"## Section {n}" in fitted for n in range(1, 11))
    assert len(fitted) <= budget


def test_a_cut_section_names_the_lines_left_out() -> None:
    fitted = excerpt(_spec(), len(_spec()) // 3, what="technical specification")

    assert "not shown: read them by line]" in fitted
    assert "every section is here" in fitted
    assert "line 19 of section 1" in fitted  # a short section is whole


def test_text_without_sections_is_still_cut_to_its_head() -> None:
    text = "x" * 1000
    assert excerpt(text, 100, what="notes").startswith("x" * 100 + "\n\n[Excerpt:")
    assert excerpt(text, 0, what="notes") == text


def test_the_same_text_and_budget_give_the_same_bytes() -> None:
    assert excerpt(_spec(), 9000, what="s") == excerpt(_spec(), 9000, what="s")


def test_a_revision_sees_every_section_of_the_previous_specification() -> None:
    from app.agents.principal_architect import _specification_excerpt

    fitted = _specification_excerpt(_spec(), len(_spec()) // 3)
    assert "FINAL-SECTION-MARKER" in fitted and "Only return the sections you are revising." in fitted
