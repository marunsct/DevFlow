"""The code declares the records the specification's domain model adopted, checked after each sprint (plan PQ.2).

Measured on the product quality audit of 2026-11-25: a medium brief's specification adopted UUID ids, created and
changed times on every record and a hashed token; the code had integer ids, no times and the token in plain text -
about twelve fields - and nothing compared the two, so the milestone review let it pass.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from app.analysis import schema_conformance
from app.graph import engineering
from test_ci_and_code_review import CONFIG, workspace  # noqa: F401 - `workspace` is the CI gate's fixture

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

DOMAIN_MODEL = [
    "- Account: id (UUID), email (str, unique, required), password_hash (str, required), created_at (datetime).",
    "- Note: id (UUID), title (str, required), owner_id (UUID FK→Account.id), created_at (datetime).",
    "- NoteStatus enum values: 'open', 'closed'.",
    "- Summary (computed, not persisted): total_notes (int), open_notes (int).",
]


def _product(root: Path, models: str) -> Path:
    project = root / "notes"
    (project / "app").mkdir(parents=True, exist_ok=True)
    (project / "app" / "models.py").write_text(models)
    return project


MODELS = '''from sqlalchemy import Column, Integer, String, DateTime


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    createdAt = Column(DateTime)
    owner_id = Column(Integer)
'''


def test_the_domain_model_s_records_are_read_in_each_way_a_specification_writes_them():
    lines = [
        "- Note { id: u64, title: String, body: String } — the shape every note endpoint returns.",
        "- Bookmark: An object representing a saved link.",
        "- id: A string holding a version-4 UUID. Unique within the collection.",
        "- url: A string starting with http.",
        "- Filter State: an interface state ('all', 'active') that is not stored.",
        "- Item: An entry with three fields: Id (integer, unique), Title (string, non-null) and Done (boolean).",
        "- Configuration: PORT (integer, default 5000) and DATA_DIR (string).",
        "- Session: token_string (opaque random string), user_id (integer). Held in an in-memory dictionary.",
    ]

    records = {r.name: r for r in schema_conformance.records_in(lines)}

    assert {name: [f.name for f in r.fields] for name, r in records.items()} == {
        "Note": ["id", "title", "body"],
        "Bookmark": ["id", "url"],
        "Item": ["Id", "Title", "Done"],
        "Session": ["token_string", "user_id"],
    }
    assert records["Bookmark"].id_kind == "uuid" and records["Note"].id_kind == "integer"
    assert records["Session"].stored is False and records["Item"].stored is True


def test_a_field_the_specification_gives_a_record_and_its_declaration_lacks_is_a_difference(tmp_path):
    project = _product(tmp_path, MODELS)
    records = schema_conformance.records_in(DOMAIN_MODEL)

    result = schema_conformance.compare(project, records)

    by_record = {d.record: d for d in result.differences}
    assert set(by_record) == {"Account", "Note"}
    assert by_record["Account"].missing == ("password_hash", "created_at")
    assert by_record["Account"].declared_at == "app/models.py line 4"
    assert by_record["Account"].code_line == "class Account(Base):"
    # `createdAt` is `created_at` spelled another way; the UUID id is still integer.
    assert by_record["Note"].missing == () and by_record["Note"].id_kind == "uuid"


def test_a_field_declared_on_another_record_does_not_count_for_this_one(tmp_path):
    project = _product(tmp_path, MODELS + "\n\nclass Audit(Base):\n    password_hash = Column(String)\n")

    result = schema_conformance.compare(project, schema_conformance.records_in(DOMAIN_MODEL[:1]))

    assert result.differences[0].missing == ("password_hash", "created_at")


def test_a_record_written_as_a_plain_object_is_looked_for_in_the_whole_product(tmp_path):
    project = tmp_path / "links"
    (project / "src").mkdir(parents=True)
    (project / "src" / "store.mjs").write_text(
        "export function add(title, url) {\n  return { id: crypto.randomUUID(), title, url, createdAt: new Date() };\n}\n")
    records = schema_conformance.records_in(["- Link: id (string, UUID), title (string), url (string), "
                                             "created_at (string), tag (string)."])

    (difference,) = schema_conformance.compare(project, records).differences

    assert difference.missing == ("tag",) and difference.declared is False


def test_a_sprint_answers_for_the_records_its_scope_names_and_the_last_sprint_for_all():
    records = schema_conformance.records_in(["- RefreshToken: id (UUID), token_hash (str).",
                                             "- Note: id (UUID), title (str)."])

    early = schema_conformance.due_records(records, "Sign in and rotate the refresh token", last_sprint=False)
    last = schema_conformance.due_records(records, "Sign in and rotate the refresh token", last_sprint=True)

    assert [r.name for r in early] == ["RefreshToken"]
    assert [r.name for r in last] == ["RefreshToken", "Note"]


def test_a_difference_becomes_a_defect_quoting_the_specification_s_line_and_the_code_s(tmp_path):
    project = _product(tmp_path, MODELS)

    defects = schema_conformance.sprint_defects(project, DOMAIN_MODEL, "", True, "database")

    (account, note) = defects
    assert account.severity == "major" and account.owner == "database"
    assert "password_hash" in account.description and "created_at" in account.description
    assert "email (str, unique, required)" in account.reproduction_steps
    assert "app/models.py line 4: `class Account(Base):`" in account.reproduction_steps
    assert account.affected_files == ["app/models.py"]
    assert "uuid" in note.description


def test_the_defects_raised_are_bounded():
    many = [f"- Record{n}: id (int), name (str), created_at (datetime)." for n in range(9)]
    conformance = schema_conformance.Conformance(
        records=[], fields=[], unique=[], id_kinds=[],
        differences=[schema_conformance.Difference(f"Record{n}", many[n], "", "", ("created_at",), declared=False)
                     for n in range(9)],
    )

    assert len(schema_conformance.defects(conformance, "backend")) == schema_conformance.MOST_SCHEMA_DEFECTS == 4


def test_the_defect_text_a_builder_reads_avoids_the_banned_words(tmp_path):
    project = _product(tmp_path, MODELS)

    defects = schema_conformance.sprint_defects(project, DOMAIN_MODEL, "", True, "database")

    texts = [schema_conformance.EXPECTED] + [
        " ".join([d.description, d.reproduction_steps, d.expected_behavior, d.actual_behavior]) for d in defects]
    assert defects and not [t for t in texts if BANNED.search(t)]


def test_the_ci_gate_raises_the_records_the_code_declares_unlike_the_specification(workspace):  # noqa: F811
    root = workspace.root
    models = root / "notes" / "src" / "store.js"
    models.parent.mkdir(parents=True, exist_ok=True)
    models.write_text("export class Note {\n  constructor(title) { this.id = 1; this.title = title; }\n}\n")
    state = {
        "repository": SimpleNamespace(root_path=str(root)),
        "milestone_plan": SimpleNamespace(delegated_tasks=[
            SimpleNamespace(title="Store notes", task_description="", specialist_role="database"),
        ]),
        "technical_specification": SimpleNamespace(domain_model=[
            "Note: id (integer), title (string, required), created_at (datetime).",
        ]),
    }

    update = engineering.ci_gate(state, CONFIG, None)

    found = [d for d in update["review_defects"] if d.source == "schema conformance"]
    assert len(found) == 1 and "created_at" in found[0].description and found[0].owner == "database"
    assert "class Note {" in found[0].reproduction_steps
