from typing import List
from app.server.plugin_store import PluginStore


def _normal(text: str) -> str:
    return " ".join(str(text or "").split())


def _items(block: str) -> list[str]:
    """`block`'s items: each line that is not indented, with the indented lines that continue it."""
    items: list[str] = []
    for line in block.splitlines():
        if items and line[:1].isspace() and line.strip():
            items[-1] += "\n" + line
        else:
            items.append(line)
    return items


def _labelled(item: str, labels: tuple[str, ...]) -> bool:
    first = item.lstrip()
    return any(first.startswith(f"- {label}:") for label in labels)


def _part_of(block: str, texts: tuple[str, ...]) -> bool:
    """Whether `block` is one of `texts`, or a part of one."""
    said = _normal(block)
    return bool(said) and any(said in _normal(text) for text in texts)


def tests_part(content: str) -> str:
    """The parts of a module about tests (`app.plugins.seed.TESTING_TEXTS` and `TESTING_LABELS`); "" for none."""
    from app.plugins.seed import TESTING_LABELS, TESTING_TEXTS

    kept: list[str] = []
    for block in content.strip().split("\n\n"):
        if _part_of(block, TESTING_TEXTS):
            kept.append(block.strip())
            continue
        items = [item for item in _items(block) if _labelled(item, TESTING_LABELS)]
        if items:
            kept.append("\n".join(items))
    return "\n\n".join(kept)


def review_lines(content: str) -> str:
    """A module less what it tells a writer to install, set up, build and run (`app.plugins.seed.HOW_TO_TEXTS` and
    `HOW_TO_LABELS`): what a reviewer can hold a product to. A block left with no more than its opening line goes."""
    from app.plugins.seed import HOW_TO_LABELS, HOW_TO_TEXTS

    kept: list[str] = []
    for block in content.strip().split("\n\n"):
        if _part_of(block, HOW_TO_TEXTS):
            continue
        items = _items(block)
        left = [item for item in items if not _labelled(item, HOW_TO_LABELS)]
        if len(left) == len(items) or any(item.strip() for item in left[1:]):
            kept.append("\n".join(left).strip())
    return "\n\n".join(block for block in kept if block)


#: The keys of the model's own guides (`app.models.guidance.PREFIX`), which are never cut to a module's parts.
_GUIDE_PREFIX = "guide:"


def _command_guides() -> set[str]:
    """The keys of the model guides about running commands: a review role has no command tool."""
    try:
        from app.models.guidance import GUIDES, PREFIX

        return {PREFIX + guide.id for guide in GUIDES if guide.area == "commands"}
    except Exception:  # noqa: BLE001 - none known
        return set()


def get_plugin_instructions(stack_keywords: List[str], role: str = "", *, tests_only: bool = False,
                            review_lines_only: bool = False) -> str:
    """Returns aggregated instructions for the given stack keywords from the database.

    `tests_only` (`QA_PROMPT_TRIMMED`): each stack module kept to its parts about tests. `review_lines_only`
    (`REVIEWER_SHAPED_PLUGIN_CONTENT`): no setup notes and no command guide, and each stack module without its how-to.
    With either, only the lessons written for this role itself, not those for every role. The model's own guides
    are never cut to a module's parts. See `app.agents.prompt_size`.
    """
    instructions = []

    store = PluginStore.shared()
    shaped = tests_only or review_lines_only
    if review_lines_only:
        from app.plugins.seed import SETUP

        left_out = _command_guides()
        stack_keywords = [k for k in stack_keywords if not k.lower().endswith(SETUP) and k.lower() not in left_out]

    # A block several modules share is given once. The seed appends the same
    # JavaScript testing notes to `javascript`, `typescript`, `node` and every
    # JavaScript framework, so a stack naming two of them carried the block
    # twice - 1,500 characters of the specialist prompt said again.
    given: set[str] = set()
    for keyword in stack_keywords:
        key = keyword.lower()
        content = store.get_instructions(key)
        if content and shaped and not key.startswith(_GUIDE_PREFIX):
            content = tests_part(content) if tests_only else content
            content = review_lines(content) if review_lines_only and content else content
        if not content:
            continue
        blocks = []
        for block in content.strip().split("\n\n"):
            normalised = " ".join(block.split())
            if normalised and normalised not in given:
                given.add(normalised)
                blocks.append(block.strip())
        if blocks:
            instructions.append(f"[{key.upper()} MODULE]\n" + "\n\n".join(blocks))

    # Lessons from earlier runs, only those the owner approved (plan item AI).
    try:
        from app.plugins.lessons import as_instructions

        learned = as_instructions(stack_keywords, role=role, own_only=shaped) if shaped else as_instructions(
            stack_keywords, role=role)
    except Exception:  # noqa: BLE001 - a lesson store that cannot be read adds nothing
        learned = ""

    if not instructions:
        return learned.lstrip("\n")

    return "\n\n=== FRAMEWORK CAPABILITIES ===\n" + "\n\n".join(instructions) + learned
