"""Whether a document delivers the capabilities the intake's success measures list.

The product intake's success measures are the one place a requirement is sure
to be stated plainly. Across the 33 stored runs whose intake required editing a
task, the sprint plan never mentioned editing in 12; the specification dropped
it outright in 3, and in both runs of `brief_low` on 2026-09-28 the
specification never named it at all. The intake's own core workflows had left
it out ("add, toggle, delete, filter") while its success
measure kept it ("add, edit, and delete"), and every later stage followed the
workflows.

What the dropped requirement has in common each time is that it is one item of
an enumeration the measure spells out. So that is what is checked, and nothing
else: every item of an "and" list must be named in the document, and at least
one item of an "or" list. Words outside such lists - "correctly", "controls",
"subsets" - are never required, which is what keeps a check like this from
sending work back over phrasing.

Nothing here reads a programming language. It compares a product's stated
requirements with the prose of the documents that plan it, in whatever stack.
"""

from __future__ import annotations

import re

#: An enumeration: "add, edit, and delete", "mobile and desktop",
#: "localStorage or a JSON file". The article after the conjunction is skipped,
#: or "or a JSON file" would end the list at "a".
_ENUMERATION = re.compile(
    r"\b([A-Za-z][\w-]*)((?:\s*,\s*[A-Za-z][\w-]*)*)\s*,?\s+(and|or)\s+"
    r"(?:(?:a|an|the)\s+)?([A-Za-z][\w-]*)",
    re.I,
)

#: A list with no conjunction: "Users can add, edit, delete tasks". Three items
#: or more, so that "Yes, please" and a clause after a comma are not read as
#: lists; "and" / "or" never count as an item, so a list that has one is left
#: to `_ENUMERATION`. One brief's acceptance criterion was written exactly this
#: way, the intake paraphrased it as "create, read, update, and delete", and
#: "edit" was never checked anywhere again.
_UNJOINED_LIST = re.compile(
    r"\b((?!(?:and|or)\b)[A-Za-z][\w-]*)((?:\s*,\s*(?!(?:and|or)\b)[A-Za-z][\w-]*){2,})\b",
    re.I,
)

#: Words that can sit in an enumeration without naming a capability. The
#: auxiliaries and negations came from one run's "shows an empty list and does
#: not error", whose plan was handed back because no sprint delivered "does".
_NOT_A_CAPABILITY = {
    "a", "all", "an", "are", "be", "both", "can", "either", "for", "in", "is", "of",
    "on", "only", "task", "tasks", "the", "to", "user", "users", "with",
    "also", "could", "did", "do", "does", "has", "have", "had", "it", "its", "may",
    "might", "must", "never", "no", "not", "should", "so", "that", "then", "this",
    "was", "were", "will", "would",
}


def _stem(word: str) -> str:
    word = word.lower()
    for suffix in ("ing", "es", "ed", "s"):
        if len(word) - len(suffix) >= 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    # A three-letter verb in the past tense. The four-letter floor above kept
    # "added" whole, and one run's plan - "add form", "add/edit/delete" - was
    # handed back for never delivering "added". Only "ed", and only down to
    # three letters: "used" and "need" are left alone.
    if word.endswith("ed") and len(word) == 5:
        return word[:-2]
    # And a three-letter verb with an "s": "runs", "adds", "logs". One run's
    # measure ended "stays under 500 lines and runs on the latest browsers";
    # the sprint that held it said "run comprehensive E2E tests", and the plan
    # was handed back twice for never delivering "runs". Not "ss": "pass" and
    # "less" are whole words.
    if len(word) == 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    # A silent "e" goes too, or "rename" is never named by "Renaming" nor
    # "delete" by "deleting". Only where five letters remain, so "store" is
    # not named by "story".
    if word.endswith("e") and len(word) - 1 >= 5:
        return word[:-1]
    return word


def named_in(word: str, text: str) -> bool:
    """Whether `text` names `word` at the start of a word, camelCase included.

    `editTask` names "edit"; "credit" does not.
    """
    stem = _stem(word)
    for match in re.finditer(re.escape(stem), text, re.I):
        at = match.start()
        if at == 0 or not text[at - 1].isalpha() or text[at].isupper():
            return True
    return False


def names_the_word(word: str, text: str) -> bool:
    """Whether `text` names `word` as a whole word, inflections allowed.

    Stricter than `named_in`, which accepts any word that starts with the stem
    ("use" in "User"). For a check whose result is written into a document:
    "edit" names "editing" and "edited", "delete" names "deletion", "create"
    names "creation"; "use" does not name "User", "add" does not name
    "address".
    """
    stem = _stem(word)
    pattern = rf"(?<![A-Za-z]){re.escape(stem)}(?:e|es|ed|d|s|ing|ion|ions|ation|ations)?(?![A-Za-z])"
    return re.search(pattern, text, re.I) is not None


def _item_named_in(item: str, text: str) -> bool:
    """`named_in`, letting a hyphenated item be named by its leading word.

    "all, active-only, or completed-only tasks" is delivered by a plan that
    filters "active" and "completed"; requiring the literal "active-only" handed
    a correct plan back. Only a leading word of five letters or more stands in,
    so "real-time" is not satisfied by "real". This errs toward not flagging,
    which is the safe side for a check that sends work back.
    """
    if named_in(item, text):
        return True
    head = item.split("-", 1)[0]
    return "-" in item and len(head) >= 5 and named_in(head, text)


def _a_clause_joined_to_a_noun(words: list[str]) -> bool:
    """Whether two "listed" words are a thing and the start of a new clause.

    A list names like things. One run's measure read "(verified by refreshing
    the browser and confirming data remains)", which pairs the end of one
    clause with the verb that opens the next, and its plan was handed back
    because no sprint delivered "confirming". Two words of which exactly one is
    an -ing form are not read as a list.
    """
    if len(words) != 2:
        return False
    first, second = (w.lower().endswith("ing") for w in words)
    return first != second


def enumerations(measure: str) -> list[tuple[bool, list[str]]]:
    """Each list inside a measure, as (every item required, items)."""
    found: list[tuple[bool, list[str]]] = []
    joined: list[tuple[int, int]] = []
    for match in _ENUMERATION.finditer(str(measure)):
        joined.append(match.span())
        words = [match.group(1)]
        words += [w.strip() for w in match.group(2).split(",") if w.strip()]
        words.append(match.group(4))
        words = [w for w in words if w.lower() not in _NOT_A_CAPABILITY]
        if len(words) >= 2 and not _a_clause_joined_to_a_noun(words):
            found.append((match.group(3).lower() == "and", words))
    for match in _UNJOINED_LIST.finditer(str(measure)):
        start, end = match.span()
        if any(start < j_end and j_start < end for j_start, j_end in joined):
            continue
        words = [match.group(1)] + [w.strip() for w in match.group(2).split(",") if w.strip()]
        words = [w for w in words if w.lower() not in _NOT_A_CAPABILITY]
        if len(words) >= 2:
            found.append((True, words))
    return found


def capabilities_never_named(text: str, measures: list[str]) -> dict[int, list[str]]:
    """Items of each measure's own lists that `text` never names.

    Returns {1-based measure number: [missing items]}, empty when nothing is.
    """
    missing: dict[int, list[str]] = {}
    for number, measure in enumerate(measures, start=1):
        for every_item, words in enumerations(measure):
            absent = [w for w in words if not _item_named_in(w, text)]
            if (every_item and absent) or (not every_item and len(absent) == len(words)):
                bucket = missing.setdefault(number, [])
                bucket.extend(w for w in absent if w not in bucket)
    return missing


__all__ = ["capabilities_never_named", "enumerations", "named_in", "names_the_word"]
