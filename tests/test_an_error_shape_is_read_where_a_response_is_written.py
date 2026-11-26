"""An error response's shape is read where a response is written, never from a type or a value that holds a status.

Measured (LF.1591): a service answering every error as `{error}` lost half its quality score's service part. The
"one error shape" check counted three shapes: the eleven real responses, a TypeScript union member
`| { ok: false; status: 400 | 422; error: string }` declaring a validation result's type, and the validation result
itself, `return { ok: false, status: 400, error: '...' }`, which the route never sends (it sends
`c.json({ error: validation.error }, validation.status)`). "The error shape the specification states" failed for the
same reason. A sweep of 70 stored products found the same misreading in two more: a validator returning
`{ valid: false, error: { status: 400, ... } }`, and a status in a response's options (`NextResponse.json(body,
{ status: 401 })`) read as a body `{status}`.

Every product here is copied verbatim from a stored run (`tests/captured/error-shapes/`; the specification and the
Rust file are whole-line excerpts).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.analysis import product_quality

CAPTURED = Path(__file__).parent / "captured" / "error-shapes"


def _scored(case: str, tmp_path: Path) -> product_quality.QualityScore:
    workspace = tmp_path / "workspace"
    shutil.copytree(CAPTURED / case, workspace)
    product = next(p.name for p in workspace.iterdir() if p.is_dir() and p.name != "docs")
    (workspace / ".project-directory").write_text(f"{product}\n")
    return product_quality.score_workspace(workspace)


def _check(result: product_quality.QualityScore, name: str) -> product_quality.Check:
    (found,) = [c for p in result.parts if p.name == "service" for c in p.checks if c.name == name]
    return found


def _shapes(check: product_quality.Check) -> list[str]:
    return [evidence.split(" x", 1)[0] for evidence in check.evidence]


def test_a_validation_result_and_its_type_are_not_error_responses_of_their_own(tmp_path):
    result = _scored("a-validation-result-carrying-its-status", tmp_path)

    one = _check(result, "one error shape")
    assert one.passed == 1.0
    assert one.evidence == ["{error} x11, first at src/app.ts:19 return c.json({ error: 'invalid JSON body' }, 400);"]
    assert _check(result, "the error shape the specification states").passed == 1.0
    assert result.counts["status codes"] == "400 404 422 500"


def test_a_validator_returning_a_status_inside_its_result_sends_no_shape(tmp_path):
    result = _scored("a-validator-returning-its-status", tmp_path)

    one = _check(result, "one error shape")
    assert one.passed == 1.0
    assert _shapes(one) == ["{error}"]


def test_a_status_in_a_response_s_options_reads_the_body_beside_it(tmp_path):
    result = _scored("a-status-in-the-response-s-options", tmp_path)

    one = _check(result, "one error shape")
    assert one.passed == 1.0
    assert _shapes(one) == ["{error, success}"]


def test_two_shapes_the_responses_really_send_are_still_found(tmp_path):
    result = _scored("two-shapes-beside-the-response-s-options", tmp_path)

    one = _check(result, "one error shape")
    assert one.passed == 0.0
    assert sorted(_shapes(one)) == ["{error, field}", "{error}"]


def test_a_variant_of_a_declared_enum_naming_a_status_is_no_error_response(tmp_path):
    """`pub enum AppError { ..., InternalServerError }`: the variant names a status; only the three `match` arms that
    turn each variant into a status answer one."""
    result = _scored("an-enum-naming-a-status", tmp_path)

    assert result.counts["error responses"] == 3
    assert result.counts["status codes"] == "400 404 500"
