"""A command piped into a filter, `a | b`, read as the commands it runs: `a` runs, and `b` is applied to its output
(plan PA.6, the rest).

There is no shell in the command tool, so `|` was refused: "'|' is a shell operator and there is no shell here".
Measured over the last 120 runs' transcripts: 27 calls piped a command, almost all of them into a filter of its output
- `mvn -q -B test 2>&1 | grep -E "(Tests run|FAILURE|ERROR ...)"`, `npm run test:acceptance 2>&1 | tail -100`,
`cat <file> | head -60`, `find / -name go -type f 2>/dev/null | head -5` - each refused, each a model call spent to
send the command again without its filter, mostly by fixers in the middle of a defect.

So the line is split at each `|` that is an item of its own (or, in a whole command line sent as one string, outside
quotes): the first command runs as any command does, under every check the tool makes; each command after a `|` is
checked as itself - the role may run that program (`sandbox.validate_command`), and it is a filter the harness can
apply to text (`FILTERS`: `head`, `tail`, `grep`, `wc`, `sort`, `uniq`, `cat`, with the options they are used with
and no file of their own) - and then applied by the harness to what the first printed. `2>&1` before a `|` sends the
command's errors through the filter too; `2>/dev/null` leaves them out. The exit code is the first command's, and
the reply says what was applied. A command after a `|` that is not such a filter is refused as before, saying why.
Always on: no new call, and a pipe a shell would have run now runs.
"""
from __future__ import annotations

import os
import re
import shlex
from typing import Any, Callable, Sequence

#: What sends the command's errors through the filter, and what drops them.
_MERGED = frozenset({"2>&1", "|&"})
_DROPPED = frozenset({"2>/dev/null", "2>", "&>/dev/null"})
#: Lines `head` and `tail` keep when given no count.
_DEFAULT_LINES = 10


class NotAFilter(ValueError):
    """A command after a `|` the harness cannot apply to text."""


def _items(command: Sequence[Any]) -> list[str]:
    """`command`'s items, a whole command line in its first item read into its words outside quotes."""
    items = [str(part) for part in command]
    if items and len(items[0].split()) > 1 and "|" in items[0]:
        try:
            lexer = shlex.shlex(items[0], posix=True, punctuation_chars="|&<>")
            lexer.whitespace_split = True
            words = list(lexer)
        except ValueError:
            return items
        # `2>&1` reads as `2`, `>&` and `1` in punctuation mode: joined back as the shell reads it.
        joined: list[str] = []
        for word in words:
            if joined and word in (">&", ">") and joined[-1] == "2":
                joined[-1] = "2" + word
            elif joined and joined[-1] in ("2>&", "2>") and word in ("1", "/dev/null"):
                joined[-1] += word
            else:
                joined.append(word)
        items = joined + items[1:]
    return items


def split(command: Any) -> tuple[list[str], list[list[str]], str] | None:
    """(the first command, each command after a `|`, what happens to its errors: "merged", "dropped" or "") for a
    piped command; None for a command with no `|` of its own."""
    if not isinstance(command, (list, tuple)) or not command:
        return None
    items = _items(command)
    if "|" not in items:
        return None
    parts: list[list[str]] = [[]]
    for item in items:
        if item == "|":
            parts.append([])
        else:
            parts[-1].append(item)
    first, stages = parts[0], parts[1:]
    if not first or any(not stage for stage in stages):
        return None
    errors = ""
    while first and first[-1] in _MERGED | _DROPPED:
        errors = "merged" if first[-1] in _MERGED else "dropped"
        first = first[:-1]
    return (first, stages, errors) if first else None


# --- the filters -----------------------------------------------------------------------------------------------------

def _count(stage: list[str], default: int = _DEFAULT_LINES) -> tuple[int, bool]:
    """(the line count `head -n N` / `tail -N` asks for, whether it counts from the start: `tail -n +N`)."""
    args = stage[1:]
    count, from_start = default, False
    at = 0
    while at < len(args):
        arg = args[at]
        value = None
        if arg in ("-n", "--lines") and at + 1 < len(args):
            value, at = args[at + 1], at + 1
        elif arg.startswith("--lines="):
            value = arg.split("=", 1)[1]
        elif re.fullmatch(r"-n[+-]?\d+", arg):
            value = arg[2:]
        elif re.fullmatch(r"-\d+", arg):
            value = arg[1:]
        else:
            raise NotAFilter(f"`{' '.join(stage)}` gives `{arg}`, which the harness does not apply")
        from_start = value.startswith("+")
        if not value.lstrip("+-").isdigit():
            raise NotAFilter(f"`{' '.join(stage)}` gives no number of lines")
        count = int(value.lstrip("+-"))
        at += 1
    return count, from_start


def _head(stage: list[str]) -> Callable[[list[str]], list[str]]:
    count, _ = _count(stage)
    return lambda lines: lines[:count]


def _tail(stage: list[str]) -> Callable[[list[str]], list[str]]:
    count, from_start = _count(stage)
    if from_start:
        return lambda lines: lines[max(count - 1, 0):]
    return lambda lines: lines[-count:] if count else []


def _basic_to_extended(pattern: str) -> str:
    """A basic regular expression as Python reads one: `\\|`, `\\(` and the like are the operators, bare ones text."""
    out, at = [], 0
    while at < len(pattern):
        character = pattern[at]
        if character == "\\" and at + 1 < len(pattern):
            following = pattern[at + 1]
            out.append(following if following in "|(){}+?" else character + following)
            at += 2
            continue
        out.append("\\" + character if character in "|(){}+?" else character)
        at += 1
    return "".join(out)


def _grep(stage: list[str]) -> Callable[[list[str]], list[str]]:
    flags: set[str] = set()
    context = {"A": 0, "B": 0}
    patterns: list[str] = []
    args = stage[1:]
    at = 0
    while at < len(args):
        arg = args[at]
        if arg in ("-e", "--regexp") and at + 1 < len(args):
            patterns.append(args[at + 1])
            at += 2
            continue
        if re.fullmatch(r"-[ABC]\d*", arg):
            number = arg[2:] or (args[at + 1] if at + 1 < len(args) else "")
            if not number.isdigit():
                raise NotAFilter(f"`{' '.join(stage)}` gives no number of lines around a match")
            for side in ("A", "B") if arg[1] == "C" else (arg[1],):
                context[side] = int(number)
            at += 1 if arg[2:] else 2
            continue
        if arg.startswith("-") and len(arg) > 1 and not patterns:
            letters = arg[1:]
            if not set(letters) <= set("EFivnchwx"):
                raise NotAFilter(f"`{' '.join(stage)}` gives `{arg}`, which the harness does not apply")
            flags |= set(letters)
            at += 1
            continue
        if patterns:
            raise NotAFilter(f"`{' '.join(stage)}` names a file, `{arg}`: a filter after `|` reads what came before it")
        patterns.append(arg)
        at += 1
    if not patterns:
        raise NotAFilter(f"`{' '.join(stage)}` gives no pattern")
    sources = [re.escape(p) if "F" in flags else (p if "E" in flags else _basic_to_extended(p)) for p in patterns]
    if "w" in flags:
        sources = [rf"\b(?:{s})\b" for s in sources]
    if "x" in flags:
        sources = [rf"^(?:{s})$" for s in sources]
    try:
        matcher = re.compile("|".join(f"(?:{s})" for s in sources), re.I if "i" in flags else 0)
    except re.error as error:
        raise NotAFilter(f"`{' '.join(stage)}`: its pattern does not read ({error})") from error

    def applied(lines: list[str]) -> list[str]:
        hits = [index for index, line in enumerate(lines) if bool(matcher.search(line)) != ("v" in flags)]
        if "c" in flags:
            return [str(len(hits))]
        keep: list[int] = []
        for index in hits:
            keep.extend(range(max(0, index - context["B"]), min(len(lines), index + context["A"] + 1)))
        return [f"{index + 1}:{lines[index]}" if "n" in flags else lines[index] for index in dict.fromkeys(keep)]

    return applied


def _wc(stage: list[str]) -> Callable[[list[str]], list[str]]:
    wanted = set("".join(arg[1:] for arg in stage[1:] if arg.startswith("-")))
    if any(not arg.startswith("-") for arg in stage[1:]) or not wanted <= set("lwcm"):
        raise NotAFilter(f"`{' '.join(stage)}` is not a count the harness applies")

    def applied(lines: list[str]) -> list[str]:
        text = "\n".join(lines) + ("\n" if lines else "")
        counts = {"l": len(lines), "w": len(text.split()), "c": len(text.encode()), "m": len(text)}
        return [" ".join(str(counts[k]) for k in ("l", "w", "c", "m") if k in (wanted or {"l", "w", "c"}))]

    return applied


def _sort(stage: list[str]) -> Callable[[list[str]], list[str]]:
    wanted = set("".join(arg[1:] for arg in stage[1:] if arg.startswith("-")))
    if any(not arg.startswith("-") for arg in stage[1:]) or not wanted <= set("rnu"):
        raise NotAFilter(f"`{' '.join(stage)}` is not a sort the harness applies")

    def key(line: str) -> Any:
        number = re.match(r"\s*(-?\d+(?:\.\d+)?)", line)
        return (0, float(number.group(1)), line) if "n" in wanted and number else (1 if "n" in wanted else 0, 0.0, line)

    def applied(lines: list[str]) -> list[str]:
        ordered = sorted(lines, key=key, reverse="r" in wanted)
        return list(dict.fromkeys(ordered)) if "u" in wanted else ordered

    return applied


def _uniq(stage: list[str]) -> Callable[[list[str]], list[str]]:
    if any(arg != "-c" for arg in stage[1:]):
        raise NotAFilter(f"`{' '.join(stage)}` is not a `uniq` the harness applies")

    def applied(lines: list[str]) -> list[str]:
        runs: list[list[Any]] = []
        for line in lines:
            if runs and runs[-1][1] == line:
                runs[-1][0] += 1
            else:
                runs.append([1, line])
        return [f"{count:7d} {line}" if stage[1:] else line for count, line in runs]

    return applied


def _cat(stage: list[str]) -> Callable[[list[str]], list[str]]:
    for arg in stage[1:]:
        if arg.startswith("-") and arg != "-":
            raise NotAFilter(f"`{' '.join(stage)}` gives `{arg}`, which the harness does not apply")
        if arg != "-":
            raise NotAFilter(f"`{' '.join(stage)}` names a file: a filter after `|` reads what came before it")
    return lambda lines: lines


#: The filters the harness applies after a `|`, by program name.
FILTERS: dict[str, Callable[[list[str]], Callable[[list[str]], list[str]]]] = {
    "head": _head, "tail": _tail, "grep": _grep, "wc": _wc, "sort": _sort, "uniq": _uniq, "cat": _cat,
}


def refusal(stages: Sequence[list[str]], role_name: str, repo_root: str | None = None) -> str:
    """Why a command after a `|` cannot be applied - the role may not run it, or it is no filter of text; ""."""
    from app.tools.sandbox import CommandNotAllowed, validate_command

    for stage in stages:
        try:
            validate_command(stage, role_name, repo_root)
        except CommandNotAllowed as refused:
            return f"After the `|`: {refused}"
        try:
            _filter(stage)
        except NotAFilter as why:
            return (f"There is no shell here. A `|` into {', '.join(f'`{name}`' for name in FILTERS)} is applied by "
                    f"the harness to what the command before it printed, but {why}. Run the command before the `|` "
                    "alone and read its output.")
    return ""


def _filter(stage: list[str]) -> Callable[[list[str]], list[str]]:
    make = FILTERS.get(os.path.basename(stage[0]))
    if make is None:
        raise NotAFilter(f"`{stage[0]}` is not one of them")
    return make(stage)


def filtered(result: Any, first: Sequence[str], stages: Sequence[list[str]], errors: str) -> Any:
    """`result` of the first command with each filter applied to what it printed, and a note saying so."""
    if not isinstance(result, dict) or "error" in result:
        return result
    stdout, stderr = str(result.get("stdout") or ""), str(result.get("stderr") or "")
    text = stdout + (("\n" if stdout and not stdout.endswith("\n") else "") + stderr if errors == "merged" else "")
    lines = text.splitlines()
    for stage in stages:
        lines = _filter(list(stage))(lines)
    shown = " | ".join(" ".join(stage) for stage in stages)
    note = (f"There is no shell here: `{' '.join(first)}` ran, and the harness applied `{shown}` to "
            + ("what it printed, its errors included" if errors == "merged" else "its output")
            + f"; the exit code is `{os.path.basename(first[0])}`'s.")
    earlier = str(result.get("note") or "")
    return {
        **result,
        "stdout": "\n".join(lines) + ("\n" if lines else ""),
        "stderr": "" if errors in ("merged", "dropped") else stderr,
        "note": (earlier + "\n\n" if earlier else "") + note,
    }


__all__ = ["FILTERS", "NotAFilter", "filtered", "refusal", "split"]
