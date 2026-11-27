"""An advice item far longer than any real one reaches the architect as its leading sentences (LF.1631, LF.1632).

Measured on one run: the testing specialist's answer, cut at the 16,000-token cap, held a tenth recommendation of
56,139 characters - real advice for one criterion, the later criteria run into it, then "The test is minimal and
sufficient. The test is deterministic and verifiable. ..." over and over, a unit too long for the loop cut at the cap -
and all of it went into the architect's request. The brief had 18 criteria, the answer room for 10, and the request
asked for one item a criterion. The fixtures are that answer's shape, shortened.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.agents.specialist_advice import SpecialistAdvice, advice_from
from app.agents.stack_selector import StackSelectorOutput, TechnologyStack
from app.state import RepositoryContext
from workflow_nodes import run_node

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: The real advice the tenth item opened with: about 2,950 characters of whole sentences.
LEADING = " ".join(
    f"Send GET /notes/{n} after creating one note with id 1 and assert the status is 404 and that no note object is "
    f"returned, since the brief says the route answers 404 when there is no note with that id."
    for n in range(2, 17)
)
#: What it then wrote to the cap: the same few sentences in a shifting order, each longer than the room left.
FILLER = [
    "The test is written in JavaScript using the request fixture of the browser runner, and it starts and stops the "
    "server itself with a unique DATA_DIR per run, so nothing is left from an earlier test.",
    "The test is minimal and sufficient, deterministic and verifiable, and it covers every non-existent id the brief "
    "speaks of, so it needs no further refinement before the architect adopts it.",
    "This is the complete test for the criterion, ready for implementation, and it proves the criterion is met when "
    "it passes against the product started the way a person starts it.",
]
RUNAWAY = LEADING + " " + " ".join(FILLER[(n * 7) % 3] for n in range(300))

REAL = [
    "AC-1: Send POST /notes with body {\"title\": \"Test\", \"body\": \"Content\"} and assert the status is 201.",
    "AC-3, AC-10: Create a note, send GET /notes/{id} with its id and assert 200 with its title and body, then send "
    "GET /notes/99999 and assert 404; between tests start the service on a fresh DATA_DIR so every test begins with "
    "an empty store, and assert on the body a caller sees rather than on the store's file. " * 4,
]


def test_an_item_past_any_real_length_keeps_its_leading_sentences_and_none_of_what_ran_on() -> None:
    kept = advice_from(SpecialistAdvice(recommendations=[*REAL[:1], RUNAWAY]))

    assert kept == [REAL[0], LEADING]


def test_items_of_the_length_real_ones_reach_are_kept_whole() -> None:
    """A long real item - several criteria proven by one test - is about 1,000 characters; nothing of it is cut."""
    kept = advice_from(SpecialistAdvice(recommendations=REAL))

    assert kept == [" ".join(item.split()) for item in REAL]


def test_one_sentence_running_far_past_the_length_is_kept_to_its_words_within_it() -> None:
    item = "AC-10: Run the program on a missing file and assert it exits 2" + ", and the test asserts it again" * 2000

    (kept,) = advice_from(SpecialistAdvice(recommendations=[item]))

    assert kept.startswith("AC-10: Run the program on a missing file and assert it exits 2, and the test asserts")
    assert 2_900 < len(kept) <= 3_000
    assert item.startswith(kept + " ")  # it ends at a whole word


CRITERIA = "\n".join(f"- The service answers request number {n} as its contract says" for n in range(1, 19))
BRIEF = f"# Notes\n\nA small service that keeps notes.\n\n## Acceptance criteria\n{CRITERIA}\n"


def _consulted(tmp_path, brief: str, recommendations: list[str]) -> tuple[list[str], str]:
    asked: list[str] = []

    def gated(state, config, *, initial_request, output_key, **kwargs):
        asked.append(initial_request["messages"][-1]["content"])
        return {output_key: SpecialistAdvice(recommendations=recommendations)}

    stack = TechnologyStack(language="Python", framework="FastAPI", frontend_framework="", database="SQLite",
                            testing_framework="pytest", product_kind="http_api", additional_tools=[])
    state = {
        "document": SimpleNamespace(text=brief),
        "stack_selection": StackSelectorOutput(technology_stack=stack, rationale="As the brief asks."),
        "product_intake": {"product_name": "Notes"},
        "repository": RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean"),
        "consultation_roles": ["testing"],
    }
    update = run_node("specialist_consultation", state, str(tmp_path), {"app.graph.workflow._run_gated_agent": gated})
    return update["specialist_advice"]["testing"], asked[0]


def test_the_architect_is_handed_the_runaway_item_as_its_leading_sentences(tmp_path) -> None:
    kept, _ = _consulted(tmp_path, BRIEF, [*REAL[:1], RUNAWAY])

    assert kept == [REAL[0], LEADING]


def test_a_brief_with_more_criteria_than_items_has_the_testing_specialist_group_them(tmp_path) -> None:
    _, asked = _consulted(tmp_path, BRIEF, REAL[:1])

    assert "18 acceptance criteria" in asked and "at most 10 recommendations" in asked
    assert "several ids" in asked
    assert "the last one is not where the rest go" in asked


def test_a_brief_with_no_more_criteria_than_items_is_asked_as_before(tmp_path) -> None:
    brief = BRIEF.replace(CRITERIA, "\n".join(CRITERIA.splitlines()[:8]))

    _, asked = _consulted(tmp_path, brief, REAL[:1])

    assert "several ids" not in asked


def test_what_the_testing_specialist_is_told_of_grouping_uses_none_of_the_banned_words(tmp_path) -> None:
    _, asked = _consulted(tmp_path, BRIEF, REAL[:1])
    note = asked[asked.index("This brief has 18 acceptance criteria"):asked.index("the rest go") + len("the rest go")]

    assert not BANNED.search(note)
