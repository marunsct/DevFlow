"""After a sprint's attempt fails, the QA lead says which locked tests no right product could pass.

The locked suite is the definition of done, and a test in it that cannot pass
holds a sprint until its attempts run out and its criteria are deferred - while
the product's fixers, who may not change the suite, spend every round on it.
The mechanical checks catch the shapes measured so far: a test that throws, an
assertion the runner does not define, a locator left behind by its own change.
Measured on one run, the shape they cannot see: a test that added one item,
then expected two in the list - "Expected: 2, Received: 1" on a page showing
exactly the one it made, through every round of the sprint's first attempt.

So when an attempt has failed, before the sprint is planned again, the QA lead
is shown each locked test still failing - its code, its criterion, the failure
and the page it failed on - and names only those that no product doing what
the criterion says could pass. Those go back to QA through the suite's repair
(`acceptance_nodes.reopen_the_suite_for`); a test the product fails because the
product is wrong is not named, and stays the product's to fix.
"""

from __future__ import annotations

import logging
import re

from pathlib import Path
from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE

#: The failing tests shown, and the characters of each one's failure.
MOST_TESTS = 6
FAILURE_CHARS = 2500


class SuiteDispute(BaseModel):
    """The QA lead's answer: the locked tests no right product could pass."""

    model_config = ConfigDict(extra="forbid")

    cannot_pass: list[str] = Field(
        default_factory=list,
        description=(
            "One line per locked test that no product doing what its criterion says could "
            "pass as written, starting with the test's name exactly as given, then why - what "
            "it asserts that its own steps never set up, or what it asks that the criterion "
            "does not. A line with no reason is not counted. Empty when every failure is the "
            "product's."
        ),
    )


class DisputeRuling(BaseModel):
    """One failing test, ruled on against a quoted standard (plan item 19, behind `STRUCTURED_DISPUTE_VERDICT`)."""

    model_config = ConfigDict(extra="forbid")

    test: str = Field(..., description="The failing test's name exactly as given.")
    the_test_is_wrong: bool = Field(
        ...,
        description=(
            "True only when no product doing what the standard below says could pass the test as written; "
            "false when a right product would pass it and this product fails it."
        ),
    )
    the_test_asserts: str = Field(..., description="What the test checks, in one sentence, from its code.")
    the_standard_says: str = Field(
        ...,
        description=(
            "The sentence of the criterion, the brief or the specification the test is judged against, quoted "
            "word for word."
        ),
    )


class SuiteDisputeWithRulings(SuiteDispute):
    """The answer with one ruling per failing test, so the harness reads the verdict, not the wording."""

    rulings: list[DisputeRuling] = Field(
        ...,
        min_length=1,
        description=(
            "One ruling for each failing test shown - required, even when every failure is the product's (then each "
            "ruling says the test is not wrong). The harness reopens a test only when its ruling says the test is "
            "wrong and quotes the standard."
        ),
    )


class _StructuredDisputeVerdict:
    """`STRUCTURED_DISPUTE_VERDICT` as the switch registry reads one: off in code and in compose until measured."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("The QA lead's dispute answer carries one ruling per failing test - wrong or right, what it asserts, "
                   "the standard's sentence quoted - and the harness reopens tests by the ruling rather than reading "
                   "its prose (plan item 19). Off until measured against the prose reading.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on("STRUCTURED_DISPUTE_VERDICT", _StructuredDisputeVerdict.ON_BY_DEFAULT)


structured_verdict_switch = _StructuredDisputeVerdict()


_SYSTEM_PROMPT = (
    "You are the QA lead. The acceptance suite you approved is locked: it is the definition "
    "of done, and only QA may change it. A sprint's attempt has failed, and some locked tests "
    "failed through every round of fixes. For each one you are shown its code, the criterion "
    "it proves, how it failed and what the page showed when it did. Decide one thing: could a "
    "product that does exactly what the criterion says pass this test as it is written? Name "
    "a test only when it could not - it asserts something its own steps never set up (more "
    "records than it created, a state it never brought about), or it asks for something the "
    "criterion and the brief do not. A test the product fails because the product is wrong is "
    "not named: that is the product's to fix. The product's code is not the standard: what "
    "it renders, returns or lacks says nothing about whether a test is right, so never open "
    "the product's files to decide what a test may expect - the criterion, the brief and the "
    "specification decide. An empty answer is a good answer. You write no code and no files."
    "\n\n" + STRUCTURED_RESPONSE_RULE
)


def build_dispute_request(
    failing: Sequence[tuple[str, str, str]], test_code: str, brief: str
) -> dict[str, list[dict[str, str]]]:
    """The QA lead's input: (test name, criterion, failure) for each, the suite's code, the brief."""
    shown = "\n\n".join(
        f"### {name}\nCriterion: {criterion}\nHow it failed:\n{message[:FAILURE_CHARS]}"
        for name, criterion, message in list(failing)[:MOST_TESTS]
    )
    content = (
        "The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"--- The locked tests that failed through every round of the attempt ---\n{shown}\n\n"
        f"--- The suite's code ---\n{test_code}\n\n"
        + (f"--- The brief ---\n{brief.strip()[:4000]}\n\n" if brief.strip() else "")
        + "Name each test above that no product doing what its criterion says could pass, "
        "and why. Leave out every one the product fails because it is wrong."
    )
    return {"messages": [{"role": "user", "content": content}]}


def create_suite_dispute_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
    allow_subdirectories: bool = True,
) -> Any:
    """The QA lead, asked which locked tests cannot pass. It reads; it writes nothing."""
    return create_role_agent(
        name="suite_dispute",
        stage="acceptance_dispute",
        system_prompt=_SYSTEM_PROMPT,
        response_format=SuiteDisputeWithRulings if structured_verdict_switch.enabled() else SuiteDispute,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root,
        allow_subdirectories=allow_subdirectories,
        can_write=False,
    )


#: A test title's criterion tags: `[AC-5][AC-12] `.
logger = logging.getLogger(__name__)

_TAGS = re.compile(r"^(?:\s*\[[^\]]+\])+\s*")


def _what_a_line_says_of(lines: Sequence[str], spellings: Sequence[str]) -> str | None:
    """What the first line naming a test by any of its spellings says after the name; None if none does."""
    for line in lines:
        lowered = line.lower()
        for spelling in spellings:
            if spelling and spelling.lower() in lowered:
                at = lowered.index(spelling.lower())
                return line[at + len(spelling):].lstrip(" `:-–—").strip()
    return None


#: A clause whose cause is what the product does: the implementation, the code, the actual answer.
_THE_PRODUCT_DOES = re.compile(
    r"\b(?:the\s+)?(?:implementation|product|code|actual(?:\s+\w+){0,2}|server|service|api|endpoint|handler|"
    r"response|returned\s+\w+)\b[^.;]{0,40}?\b(?:includes?|returns?|contains?|has|have|adds?|sends?|responds?|gives?|"
    r"lacks?|omits?|parses?|sets?|uses?|loads?|reads?|writes?|persists?|stores?|saves?|ignores?|throws?|crash\w*|"
    r"never\s+\w+|fails?\s+to|cannot|can't|did\s+not|didn't|does\s+not|doesn't|is\s+not|isn't|are\s+not|aren't)\b", re.I)
#: A clause whose subject is the test asking for what the standard does not give.
_THE_TEST_OVERASKS = re.compile(
    r"\b(?:test|it|assert\w*|expect\w*|asks?|requires?)\b[^.;]{0,100}?\b(?:criterion|criteria|brief|specification|spec|"
    r"interface)\b[^.;]{0,40}?\b(?:does\s+not|do\s+not|doesn't|never|nowhere|not\s+(?:require|mention|state|say|specify|define|ask))\b",
    re.I)


#: A predicate about what the product does, whatever its subject - a product's own symbol as often as "the product":
#: `StorageService.load() is never called`, `data is not loaded on startup`, `the handler never runs`.
_A_PRODUCT_PREDICATE = re.compile(
    r"\b(?:is|are|was|were|gets?)\s+(?:never|not)\s+\w+(?:ed|en)\b|"
    r"\bnever\s+(?:called|invoked|runs?|executed|loaded|loads|read|reads|written|writes|persisted|persists|saved|saves|"
    r"stored|stores|implemented|happens|reached|triggered|set|initiali[sz]ed|awaited|registered|mounted|wired)\b|"
    r"\b(?:is|are)\s+(?:missing|undefined|absent|unimplemented|hard-?coded)\b", re.I)


#: A clause about the test's own steps, in the words the dispute asks for ("it asserts something its own steps never
#: set up"), or saying it fails whatever the product does. Measured on one run: "it asserts that updated.title equals
#: a freshly generated random string ...; its own steps never set up" matched "never set" as the product's, and a
#: test no product can pass stayed locked.
_THE_TEST_S_OWN = re.compile(
    r"\b(?:its|the\s+test'?s?)\s+own\s+(?:steps|setup|calls?|requests?|data|values?|arguments?)\b|"
    r"\b(?:would|will|must)\s+fail\s+(?:even|whatever|for\s+any|on\s+any|against\s+any)\b", re.I)


def judged_by_the_code(why: str) -> bool:
    """Whether a reason sets a test aside for what the product does rather than for what the criterion says.

    Measured on two runs: "the implementation includes createdAt and updatedAt, which are not part of the criterion"
    set aside the tests of a criterion that lists a record's three fields; "the implementation parses the body as
    JSON regardless of header and responds with 200 instead of the 415 the specification defines" set aside the
    specification's own test. Each is the product departing from the standard, which is the product's to fix. A
    reason is the product's only when no clause of it says the test asks for what the standard does not.
    """
    clauses = [clause for clause in re.split(r"[.;]", str(why or "")) if clause.strip()]
    if any(_THE_TEST_OVERASKS.search(clause) or _THE_TEST_S_OWN.search(clause) for clause in clauses):
        return False
    return any(_THE_PRODUCT_DOES.search(clause) or _A_PRODUCT_PREDICATE.search(clause) for clause in clauses)


def _tests_the_rulings_name(rulings: Sequence[Any], failing_names: Sequence[str]) -> list[str]:
    """The repair feedback for each failing test a ruling calls wrong, with what it asserts and the standard quoted.

    Read by the field, not the wording: tonight's prose classifier filed "its own steps never set up" as a reason about
    the product (LF.405) and needed four patches. A ruling with no quoted standard reopens nothing.
    """
    named = []
    for ruling in rulings:
        test = " ".join(str(getattr(ruling, "test", "") or "").split())
        quoted = " ".join(str(getattr(ruling, "the_standard_says", "") or "").split())
        asserts = " ".join(str(getattr(ruling, "the_test_asserts", "") or "").split())
        if not getattr(ruling, "the_test_is_wrong", False) or len(quoted.split()) < 3 or not asserts:
            continue
        name = next((n for n in failing_names if n == test or _TAGS.sub("", n).strip() == _TAGS.sub("", test).strip()), None)
        if name and not any(line.startswith(f"`{name}`") for line in named):
            named.append(
                f"`{name}` cannot pass for any product that does what its criterion says: it checks that {asserts}, "
                f"and the standard says \"{quoted}\". Fix the test so that it checks what the standard says."
            )
    return named


def tests_it_names(answer: Any, failing_names: Sequence[str]) -> list[str]:
    """The suite's repair feedback for each failing test the answer names.

    By its name, or by its title without the criterion tags, in any case: one
    run's QA lead named all three tests that could not pass as
    "ac-ac5.spec.js: filter tasks by status cannot ..." - right about each,
    and none of them reopened while only the exact name counted. Only tests
    that are failing can be named, so a loose match names nothing else.
    """
    rulings = list(getattr(answer, "rulings", None) or []) if structured_verdict_switch.enabled() else []
    if rulings:
        return _tests_the_rulings_name(rulings, failing_names)
    lines = [" ".join(str(line).split()) for line in getattr(answer, "cannot_pass", None) or []]
    named = []
    # A bare tag stands for a test only when no other failing test carries it: two tests of one criterion named as
    # "[AC-4]" reopened both, counted both against the cap, and told QA to change the right one (deep review, A3).
    leading = [name.split()[0] if name.startswith("[") else name for name in failing_names]
    for name, clean_tag in zip(failing_names, leading):
        alone = leading.count(clean_tag) == 1
        why = _what_a_line_says_of(lines, (name, _TAGS.sub("", name).strip(), clean_tag if alone else ""))
        # A name with no reason is not a judgement: one run's QA lead listed
        # nine names bare, eight of them a later sprint's unbuilt work.
        if why and len(why.split()) >= 3 and judged_by_the_code(why):
            # The code is not the standard (the prompt's rule): a test set aside for what the product does stays.
            logger.warning("The QA lead set `%s` aside for what the product does, not what its criterion says; it stays locked: %s", name, why[:200])
            continue
        if why and len(why.split()) >= 3:
            named.append(
                f"`{name}` cannot pass for any product that does what its criterion says"
                + (f": {why}" if why else "")
                + ". Fix the test so that it checks what the criterion says."
            )
    return named


__all__ = [
    "SuiteDispute",
    "build_dispute_request",
    "create_suite_dispute_agent",
    "judged_by_the_code",
    "tests_it_names",
]
