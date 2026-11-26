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


# LF.1592: three more misreadings the same sweep found, each a fact of one language in the language table.


def test_docstrings_describing_the_responses_are_neither_responses_nor_shapes(tmp_path):
    """Measured: a FastAPI service answering every error as `{detail}` lost both shape checks to its docstrings -
    "returns HTTP 422 with {"detail": ...}" and "If exists, raises HTTPException(409)" read as responses, the last two
    in shapes `{username}` and `{token}` taken from the code below them."""
    result = _scored("docstrings-that-describe-the-responses", tmp_path)

    one = _check(result, "one error shape")
    assert one.passed == 1.0
    assert _shapes(one) == ["{detail}"]
    assert not any('"""' in evidence or "HTTP 422 with" in evidence for evidence in one.evidence)
    assert _check(result, "the error shape the specification states").passed == 1.0


def test_a_php_array_body_is_read_and_a_later_assignment_is_not(tmp_path):
    """Measured: `JsonResponse::json($response, ['message' => 'Body is required'], 400)` was not read, and
    `$title = $body['title'];` three lines below was read as a body `{title}`."""
    result = _scored("php-array-bodies", tmp_path)

    one = _check(result, "one error shape")
    assert _shapes(one) == ["{message}"]
    assert one.evidence[0].startswith("{message} x22, first at src/Service.php:63 ")
    assert _check(result, "the error shape the specification states").passed == 1.0


def test_rust_error_values_built_before_the_response_are_not_responses(tmp_path):
    """Measured: `.map_err(|e| AppError::BadRequest(...))` and `Err(AppError::NotFound(...))` in the store were read as
    error responses, one in a shape `{AppError}`; only the `IntoResponse` arms that give each variant its
    `StatusCode` answer one."""
    result = _scored("rust-error-values-built-before-the-response", tmp_path)

    one = _check(result, "one error shape")
    assert one.passed == 1.0
    assert _shapes(one) == ["{error}"]
    assert result.counts["error responses"] == 3
    assert result.counts["status codes"] == "400 404 422"
    assert _check(result, "the error shape the specification states").passed == 1.0
