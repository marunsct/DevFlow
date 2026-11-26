"""Does the code declare the records the specification's domain model adopted (plan PQ.2)?

Measured on the product quality audit of 2026-11-25: a medium brief's specification adopted UUID ids, created and
changed times on every record, a hashed refresh token and per-person ownership of categories and tags; the code had
integer ids, no times, the token in plain text and names unique for everyone. The milestone review saw the difference
and let it pass, and nothing else compared the two, so about twelve adopted fields were simply never built.

This compares them mechanically, with no parser per language: the domain model is read for its records (a name and
its fields, each with what the line says of it: unique, required, the id's kind), each record's declaration is found
in the product's source by a small table of how each language declares one (a class, a struct, a table), and each
field is looked for, by name, in that declaration. A name is compared without case or underscores, so `created_at`,
`createdAt` and `CreatedAt` are one name. A record nothing declares (a plain object in a script) is looked for in the
whole product.

`differences` is the comparison; `defects` turns it into defects a builder fixes, each quoting the specification's
line and the code's; `due_records` keeps the records a sprint's scope names (every record at the last sprint).
`app.analysis.product_quality` reads the same comparison for the run's quality score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.stacks.languages import BUILT_BY_NAME, LANGUAGES, NOT_THE_PRODUCT

# --------------------------------------------------------------------------------------------------------------
# The specification's side: records and their fields.
# --------------------------------------------------------------------------------------------------------------

#: The first word of what a field's parentheses (or a `name: Type` pair) say, when it is a type or a constraint: the
#: sign that the identifier before it is a field and not a word of prose (`edited (editingId ...)` is prose).
_TYPE_WORD = (
    r"(?:(?i:str|string|text|int|integer|number|numeric|bool|boolean|uuid|guid|date|datetime|time|timestamp|"
    r"timestamptz|float|double|decimal|real|varchar|char|bigint|smallint|serial|bigserial|json|jsonb|list|array|"
    r"dict|map|object|enum|blob|bytes|binary|opaque|optional|nullable|required|unique|positive|non-empty|nonempty|"
    r"non-null|[ui](?:8|16|32|64|128|size)|f32|f64|vec|option|primary|auto|auto-generated|autoincrement|fk|foreign|"
    r"iso|url|email|hash|hashed|long|short|byte|any|null)\b|[A-Z][A-Za-z0-9_]*)"
)
#: `name (type, ...)`: a field and what its parentheses say of it.
#: The name may be in backticks (`` `username` (unique string) ``); a name a backtick closes on its left is not one.
_PAREN_FIELD = re.compile(r"(?<![.\w'\"`])`?([A-Za-z_][A-Za-z0-9_]*)`?\s*\(\s*(" + _TYPE_WORD + r"[^)]*)\)")
#: `name: Type` - a struct-like spelling (`Note { id: u64, title: String }`).
_COLON_FIELD = re.compile(r"(?<![.\w'\"`])([a-z_][A-Za-z0-9_]*)\s*:\s*(" + _TYPE_WORD + r"[^,;}]*)")
#: A record's line: an optional bullet, the record's name, then `:`, `{`, `(` or a dash.
_RECORD_LINE = re.compile(
    r"^(?P<indent>\s*)(?:[-*+]\s+)?(?P<name>[^:{(—–]+?)\s*(?:\([^)]*\))?\s*(?P<separator>:|\{|—|–|\s-\s)(?P<rest>.*)$")
#: A heading or a bold name on a line of its own, whose fields follow as bullets.
_RECORD_HEADING = re.compile(r"^\s*(?:#{2,6}\s+|[-*+]\s+)?\**`?(?P<name>[A-Z][A-Za-z0-9_]*)`?\**\s*:?\s*$")
_CAPITALISED = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
_LOWER_IDENTIFIER = re.compile(r"^[a-z_][A-Za-z0-9_]*$")
#: A record that is never stored: computed for a response, or held only while the process runs.
_NOT_STORED = re.compile(r"\b(?:computed|not persisted|never persisted|ephemeral|in-memory|transient|not stored|never stored)\b", re.I)
#: A table name the record's line gives: "Stored in the `accounts` table", "table 'notes'".
_TABLE_NAMED = re.compile(r"""[`'"]([A-Za-z_][A-Za-z0-9_]*)[`'"]\s*(?:\w+\s+)?table\b|\btable\s+[`'"]([A-Za-z_][A-Za-z0-9_]*)[`'"]""", re.I)
_UUID = re.compile(r"\b(?:uuid\w*|guid)\b|randomuuid|uuid", re.I)
_INTEGER = re.compile(r"\b(?:int|integer|number|serial|bigserial|bigint|autoincrement|[ui](?:8|16|32|64|size))\b", re.I)


@dataclass(frozen=True)
class SpecField:
    """One field of a record, as the specification's line states it."""

    name: str
    text: str
    unique: bool = False
    required: bool = False


@dataclass
class SpecRecord:
    """One record of the specification's domain model."""

    name: str
    line: str
    fields: list[SpecField] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    stored: bool = True

    @property
    def id_kind(self) -> str:
        """"uuid", "integer" or "" - what the specification states of the record's id."""
        for one in self.fields:
            if one.name.lower() == "id":
                if _UUID.search(one.text):
                    return "uuid"
                if _INTEGER.search(one.text):
                    return "integer"
        return ""


def _clean(text: str) -> str:
    return text.replace("**", "").replace("`", "").strip()


#: Capitalised words that start prose, not a type: `id: A string ...`.
_NOT_A_TYPE = frozenset({"A", "An", "The", "This", "That", "Each", "Every", "One", "Its", "It"})


#: What stands before a field where a specification lists it: the start of the line, a list's separator or bracket,
#: a dash, a sentence's end, a label's colon (`Fields:`, `Attributes:`), the `and` / `or` of a list's last item, or
#: a word that opens a list ("fields are", "a record with", "containing", "a single field"), or the field's own type
#: written before it ("an integer ID (auto-incrementing)", "a string Title (required)").
_A_LIST_GOES_ON = re.compile(
    r"(?:^|[,;:({\[.—–-]|\b(?i:and|or|with|containing|contains?|including|includes?|are|has|have|holds?|carries|"
    r"carry|of|plus|fields?|keys?|columns?|properties|property|attributes?|members?|str|string|text|int|integer|"
    r"number|bool|boolean|uuid|date|datetime|timestamp|float|decimal))$")


def _in_a_list(text: str, start: int) -> bool:
    """Whether the field form at `start` stands where a list names a field, not as a word inside a sentence.

    Measured on one run: "Token: Opaque string identifier ... Generated on successful signin (POST /signin)." was read
    as the field `signin` of type `POST`, and a fix that added it to the tokens table broke a unit test, three times.
    """
    before = re.sub(r"[\s`*]+$", "", text[:start])
    return bool(_A_LIST_GOES_ON.search(before))


def _fields_in(text: str, braced: bool = False) -> list[SpecField]:
    """The fields a record's line lists: `name: Type` pairs inside braces, else `name (type, ...)`, else pairs - each
    where a list names it (`_in_a_list`), never a word of a sentence about the record."""
    if braced:
        text = text.split("}", 1)[0]
    found: dict[str, SpecField] = {}
    for pattern in ((_COLON_FIELD,) if braced else (_PAREN_FIELD, _COLON_FIELD)):
        if found:
            break
        for match in pattern.finditer(text):
            name, said = match.group(1), match.group(2)
            if not _in_a_list(text, match.start()):
                continue
            if (name.isupper() and len(name) > 1) or said.split()[0].strip(",.;") in _NOT_A_TYPE:
                # An environment setting (`PORT`, `DATA_DIR`) or a sentence, not a field.
                continue
            if name.lower() not in found:
                found[name.lower()] = _field(name, said)
    return list(found.values())


def _field(name: str, said: str) -> SpecField:
    return SpecField(
        name=name, text=said,
        unique=bool(re.search(r"\bunique\b", said, re.I)),
        required=bool(re.search(r"\b(?:required|non-null|not null|non-empty|nonempty)\b", said, re.I)),
    )


def records_in(lines: Iterable[str]) -> list[SpecRecord]:
    """The stored records of a domain model, from its lines (the document's bullets, or the specification's list).

    A record is a line that starts with a capitalised name and lists fields, inline (`User: id (UUID), email (str,
    unique)`, `Note { id: u64, title: String }`) or as the bullets that follow it (`id: A string ...`). Lines that
    list no field - an enum, a type alias, a note on storage - are not records. A record the line says is never
    stored (computed for a response, held in memory) is kept with `stored` False.
    """
    records: list[SpecRecord] = []
    current: SpecRecord | None = None
    takes_bullets = False
    for raw in lines:
        for line in str(raw or "").splitlines():
            if not line.strip() or line.lstrip().startswith("## "):
                continue
            heading = _RECORD_HEADING.match(_clean(line))
            if heading:
                current = SpecRecord(name=heading.group("name"), line=line.strip())
                records.append(current)
                takes_bullets = True
                continue
            match = _RECORD_LINE.match(line)
            name = _clean(match.group("name")) if match else ""
            if match and _CAPITALISED.match(name):
                current = SpecRecord(name=name, line=line.strip(),
                                     fields=_fields_in(match.group("rest"), match.group("separator") == "{"))
                current.stored = not _NOT_STORED.search(line)
                current.tables = [a or b for a, b in _TABLE_NAMED.findall(line)]
                records.append(current)
                takes_bullets = not current.fields
                continue
            if match and current is not None and takes_bullets and _LOWER_IDENTIFIER.match(name):
                current.fields.append(_field(name, match.group("rest")))
                current.line = f"{current.line} / {line.strip()}" if len(current.line) < 400 else current.line
                continue
            if match and name and not _LOWER_IDENTIFIER.match(name):
                # Another kind of entry (`Tasks Array: ...`) ends the record before it.
                current, takes_bullets = None, False
    return [record for record in records if record.fields]


def domain_model_lines(specification_text: str) -> list[str]:
    """The lines of a specification document's "Domain Model" section."""
    lines, inside = [], False
    for line in (specification_text or "").splitlines():
        if re.match(r"^#{1,3}\s", line):
            inside = bool(re.match(r"^#{1,3}\s+domain\s+model\b", line, re.I))
            continue
        if inside:
            lines.append(line)
    return lines


# --------------------------------------------------------------------------------------------------------------
# The code's side: where each record is declared.
# --------------------------------------------------------------------------------------------------------------

_MODIFIERS = r"(?:(?:pub(?:\([^)]*\))?|export|public|private|protected|internal|static|abstract|sealed|partial|data|default|final|readonly|declare|open)\s+)*"
#: A schema object in a script: `const Task = sequelize.define(...)`, `const NoteSchema = new Schema(...)`.
_JS_SCHEMA = (r"^\s*(?:export\s+)?(?:const|let|var)\s+{name}(?:Schema|Model)?\s*=\s*(?:new\s+)?[\w.]*"
              r"(?:model|define|Schema|object|table)\b")
#: How each language declares a record by its name (`{name}`), by the language's name in `app.stacks.languages`.
DECLARATIONS: dict[str, tuple[str, ...]] = {
    "python": (r"^\s*class\s+{name}\b", r"^\s*{name}\s*=\s*[\w.]*Table\("),
    "javascript": (r"^\s*" + _MODIFIERS + r"class\s+{name}\b", _JS_SCHEMA),
    "typescript": (r"^\s*" + _MODIFIERS + r"(?:class|interface|type)\s+{name}\b", _JS_SCHEMA),
    "go": (r"^\s*type\s+{name}\s+struct\b",),
    "rust": (r"^\s*" + _MODIFIERS + r"struct\s+{name}\b",),
    "java": (r"^\s*" + _MODIFIERS + r"(?:class|record|interface)\s+{name}\b",),
    "kotlin": (r"^\s*" + _MODIFIERS + r"(?:class|interface|object)\s+{name}\b",),
    "csharp": (r"^\s*" + _MODIFIERS + r"(?:class|record|struct|interface)\s+{name}\b",),
    "ruby": (r"^\s*class\s+{name}\b",),
    "php": (r"^\s*" + _MODIFIERS + r"class\s+{name}\b",),
}
#: Declarations any file may hold under a table's name: SQL, a schema file, a migration, an ORM's table name.
_TABLE_DECLARATIONS = (
    r"(?i)\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?[`\"\[]?{name}\b",
    r"(?i)table\w*\s*(?:\(|=|:)\s*[`'\"]{name}[`'\"]",
    r"^\s*model\s+{name}\s*\{",
)
#: Where one declaration ends: the next declaration of anything, or a function.
_NEXT_DECLARATION = re.compile(
    r"^\s*" + _MODIFIERS + r"(?:class|struct|interface|type|record|enum|object|def|fn|func|function|model|impl)\s+[A-Za-z_<]"
    r"|(?i:\bcreate\s+table\b)"
)
#: The most lines one declaration is read for.
MOST_DECLARATION_LINES = 80
#: Source files the data layer may be written in besides the languages' own: schema and migration files.
_DATA_SUFFIXES = (".sql", ".prisma", ".graphql", ".gql")
#: Folders that hold no product code, besides what the language table names.
_NOT_PRODUCT_CODE = frozenset({
    "tests", "test", "__tests__", "spec", "e2e", "acceptance", "cypress", "playwright-report", "test-results",
    "coverage", ".harness", "docs", "data", ".pytest_cache", "fixtures",
})
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _language_of(path: Path) -> str:
    for row in LANGUAGES:
        if path.suffix.lower() in row.suffixes:
            return row.name
    return ""


def product_source_files(project: Path) -> list[Path]:
    """The product's own source files: every language's, plus markup, stylesheets and schema files; no tests."""
    from app.analysis.file_kinds import is_test
    from app.analysis.walk import files_under

    suffixes = {suffix for row in LANGUAGES for suffix in row.suffixes} | set(_DATA_SUFFIXES) | {
        ".html", ".htm", ".vue", ".svelte", ".astro", ".css", ".scss", ".sass", ".less",
    }
    skip = NOT_THE_PRODUCT | BUILT_BY_NAME | _NOT_PRODUCT_CODE
    found = []
    for path in files_under(project, skip=skip, skip_hidden=True):
        relative = path.relative_to(project).as_posix()
        if path.suffix.lower() not in suffixes or ".egg-info/" in relative or is_test(relative):
            continue
        if re.search(r"(^|/)[^/]*\.(?:config|setup)\.[cm]?[jt]s$", relative) or relative.endswith(".d.ts"):
            continue
        found.append(path)
    return found


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def _plural(word: str) -> str:
    if word.endswith("y") and not word.endswith(("ay", "ey", "oy", "uy")):
        return word[:-1] + "ies"
    return word + ("es" if word.endswith(("s", "x", "z", "ch", "sh")) else "s")


def table_names(record: SpecRecord) -> list[str]:
    """The names a table holding this record is likely to have: the line's own, then the record's name spelled as one."""
    snake = _snake(record.name)
    return list(dict.fromkeys([*record.tables, snake, _plural(snake), record.name.lower(), _plural(record.name.lower())]))


def normal(name: str) -> str:
    """A name without case, underscores or dashes: `created_at`, `createdAt` and `CreatedAt` are one."""
    return re.sub(r"[_\-]", "", name).lower()


@dataclass(frozen=True)
class Declaration:
    """Where the code declares a record: the file, the first line (from 1), and the lines read as its body."""

    file: str
    line: int
    text: str
    body: str


def declarations_of(record: SpecRecord, sources: dict[Path, str], project: Path) -> list[Declaration]:
    """Every declaration of the record in the product's source: by its name in its language's table, or as a table."""
    found: list[Declaration] = []
    for path, text in sources.items():
        language = _language_of(path)
        patterns = [p.replace("{name}", re.escape(record.name)) for p in DECLARATIONS.get(language, ())]
        for table in table_names(record):
            patterns += [p.replace("{name}", re.escape(table)) for p in _TABLE_DECLARATIONS]
        compiled = [re.compile(p, re.M) for p in patterns]
        lines = text.splitlines()
        for number, line in enumerate(lines):
            if not any(pattern.search(line) for pattern in compiled):
                continue
            body = [line]
            for following in lines[number + 1: number + MOST_DECLARATION_LINES]:
                if _NEXT_DECLARATION.search(following):
                    break
                body.append(following)
            found.append(Declaration(path.relative_to(project).as_posix(), number + 1, line.strip(), "\n".join(body)))
    return found


def _names_in(text: str) -> set[str]:
    return {normal(name) for name in _IDENTIFIER.findall(text)}


@dataclass(frozen=True)
class Difference:
    """One record whose declaration lacks what the specification gives it."""

    record: str
    spec_line: str
    declared_at: str
    code_line: str
    missing: tuple[str, ...]
    id_kind: str = ""
    declared: bool = True


@dataclass
class Conformance:
    """The comparison of one product's code with its specification's domain model."""

    records: list[SpecRecord]
    differences: list[Difference]
    #: (record, field) of every field the specification gives a stored record, and whether the code declares it.
    fields: list[tuple[str, str, bool]]
    #: (record, field, declared unique) of every field the specification calls unique, other than an id.
    unique: list[tuple[str, str, bool]]
    #: (record, what the specification states, whether the code agrees) for every stated id kind.
    id_kinds: list[tuple[str, str, bool]]


def _sources(project: Path) -> dict[Path, str]:
    return {path: _read(path) for path in product_source_files(project)
            if path.suffix.lower() not in {".css", ".scss", ".sass", ".less"}}


def compare(project: Path, records: Sequence[SpecRecord], sources: dict[Path, str] | None = None) -> Conformance:
    """Compare each stored record with its declarations (or the whole product, when nothing declares it)."""
    sources = _sources(project) if sources is None else sources
    everything = "\n".join(sources.values())
    everywhere = _names_in(everything)
    differences, fields, unique, id_kinds = [], [], [], []
    for record in records:
        if not record.stored:
            continue
        declared = declarations_of(record, sources, project)
        bodies = [d.body for d in declared]
        # A declaration that extends another (`class Task(Base, TimestampMixin)`) has that one's fields too.
        for one in list(declared):
            kind = re.search(r"\b(?:class|interface|record|struct)\s+\w+(.*)$", one.text)
            for base in re.findall(r"\b([A-Z][a-z]\w*)\b", kind.group(1)) if kind else []:
                bodies += [d.body for d in declarations_of(SpecRecord(base, ""), sources, project)]
        body = "\n".join(bodies)
        names = _names_in(body) if declared else everywhere
        missing = tuple(f.name for f in record.fields if normal(f.name) not in names)
        fields += [(record.name, f.name, f.name not in missing) for f in record.fields]
        lines = (body if declared else everything).splitlines()
        for one in record.fields:
            if one.unique and normal(one.name) != "id":
                unique.append((record.name, one.name, any(
                    re.search(r"unique", line, re.I) and normal(one.name) in _names_in(line) for line in lines)))
        kind_wrong = ""
        if record.id_kind == "uuid" and declared:
            # Wrong only on evidence: the declaration gives its id an integer kind. A string id (`id: string`) may hold
            # a UUID made elsewhere.
            integer_id = any(
                "id" in _names_in(line) and _INTEGER.search(line) and not _UUID.search(line) for line in body.splitlines())
            agrees = bool(_UUID.search(body)) or not integer_id
            id_kinds.append((record.name, "uuid", agrees))
            if not agrees:
                kind_wrong = "uuid"
        if missing or kind_wrong:
            first = declared[0] if declared else None
            differences.append(Difference(
                record=record.name, spec_line=record.line,
                declared_at=f"{first.file} line {first.line}" if first else "",
                code_line=first.text if first else "", missing=missing, id_kind=kind_wrong, declared=bool(declared),
            ))
    return Conformance(list(records), differences, fields, unique, id_kinds)


# --------------------------------------------------------------------------------------------------------------
# A sprint's records, and the defects a builder fixes.
# --------------------------------------------------------------------------------------------------------------

#: How many records' differences one sprint check raises as defects; each lists at most `MOST_FIELDS_NAMED` fields.
MOST_SCHEMA_DEFECTS = 4
MOST_FIELDS_NAMED = 10


def _spoken(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).lower()


def due_records(records: Sequence[SpecRecord], scope_text: str, last_sprint: bool) -> list[SpecRecord]:
    """The records a sprint answers for: every one at the last sprint, else those its scope names.

    A record is named by its own name, its name spelled as words (`refresh token`), or a table name for it.
    """
    if last_sprint:
        return list(records)
    text = (scope_text or "").lower()
    due = []
    for record in records:
        spellings = {record.name.lower(), _spoken(record.name), *table_names(record)}
        if any(re.search(r"(?<![a-z0-9_])" + re.escape(s) + r"(?![a-z0-9_])", text) for s in spellings if s):
            due.append(record)
    return due


def _quoted(text: str, most: int = 300) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= most else text[: most - 3] + "..."


#: What a builder is asked to do about a difference: declare what the specification adopted, under its names.
EXPECTED = (
    "{record} is declared with every field the specification's domain model gives it, under the same names and of "
    "the kinds it states. Add each missing field where {record} is declared (or rename the field that stands for it "
    "to the specification's name). What each response returns stays as the specification's API contract states."
)


def defects(conformance: Conformance, owner: str, most: int = MOST_SCHEMA_DEFECTS,
            keep: Callable[[Any], bool] | None = None) -> list:
    """One major defect per record that differs, with the specification's line and the code's quoted; at most `most`
    of those `keep` keeps, so a finding left out never takes the place of one raised."""
    from app.agents.specialists import ReportedDefect

    found = []
    for difference in conformance.differences:
        if len(found) >= most:
            break
        named = list(difference.missing[:MOST_FIELDS_NAMED])
        more = len(difference.missing) - len(named)
        lacks = []
        if named:
            lacks.append(f"field(s) {', '.join(named)}" + (f" and {more} more" if more > 0 else ""))
        if difference.id_kind:
            lacks.append(f"an id of the kind the specification states ({difference.id_kind})")
        where = (f"declared at {difference.declared_at}: `{_quoted(difference.code_line, 160)}`"
                 if difference.declared else "declared nowhere in the product's source")
        found.append(ReportedDefect(
            description=f"Schema conformance: {difference.record} lacks {' and '.join(lacks)} "
                        f"that the specification's domain model gives it",
            severity="major",
            reproduction_steps=(f"The specification's domain model says: `{_quoted(difference.spec_line)}`. "
                                f"The code has {difference.record} {where}."),
            expected_behavior=EXPECTED.format(record=difference.record),
            actual_behavior=f"{difference.record} is {where}, without {' or '.join(lacks)}.",
            affected_files=[difference.declared_at.split(" line ")[0]] if difference.declared else [],
            owner=owner,
            regression_test_required=False,
        ))
        if keep is not None and not keep(found[-1]):
            found.pop()
    return found


def sprint_defects(project: Path, domain_model: Sequence[str], scope_text: str, last_sprint: bool, owner: str,
                   keep: Callable[[Any], bool] | None = None) -> list:
    """The schema-conformance defects for one sprint: its due records compared with the code (PQ.2); `keep` leaves
    out a finding before the cap (`defects`)."""
    records = due_records([r for r in records_in(domain_model) if r.stored], scope_text, last_sprint)
    if not records or not project.is_dir():
        return []
    return defects(compare(project, records), owner, keep=keep)
