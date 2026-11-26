"""A word in a sentence about a record is not one of its fields; the fields a specification lists still are (LF.1549).

Measured on one run: the domain model's line "Token: Opaque string identifier for an authenticated session. Generated
on successful signin (POST /signin). ..." was read as the field `signin` of type `POST`. The gate raised "Token lacks
field(s) signin", and each rewrite that added it to the tokens table broke a unit test that passed, three times, until
the defect went to a person. Read over 146 stored specifications, 13 such words were fields (`len`, `array`, `fails`,
`SQLite`, ...); every listed field is still read.
"""
from __future__ import annotations

from pathlib import Path

from app.analysis.schema_conformance import domain_model_lines, records_in

CAPTURED = Path(__file__).parent / "captured"


def _fields(captured: str) -> dict[str, list[str]]:
    text = (CAPTURED / captured).read_text(encoding="utf-8")
    return {record.name: [f.name for f in record.fields] for record in records_in(domain_model_lines(text))}


def test_a_word_in_a_sentence_about_how_a_record_is_made_is_not_its_field():
    found = _fields("technical-specification-a-token-generated-on-signin.md")

    assert "signin" not in found.get("Token", []), "the Token line lists no field"


def test_a_word_in_a_sentence_after_a_field_list_is_not_a_field():
    found = _fields("technical-specification-domain-model-word-statistics.md")

    assert found["WordStatistics"] == ["word_count", "line_count", "character_count"], "not `len` of `len(text)`"


def test_fields_listed_after_a_label_still_are_fields():
    found = _fields("technical-specification-domain-model-notes.md")

    assert found["Note"] == ["id", "title", "body"], "not `tests` of a sentence about the acceptance tests"
    assert found["NoteError"] == ["title"]


def test_fields_listed_in_braces_still_are_fields():
    found = _fields("technical-specification-domain-model-a-shop.md")

    assert found["Product"] == ["id", "vendorId", "name", "description", "price", "stock", "category", "images", "slug",
                                "createdAt", "updatedAt"]
    assert found["OrderItem"] == ["id", "orderId", "productId", "quantity", "priceAtPurchase"]
