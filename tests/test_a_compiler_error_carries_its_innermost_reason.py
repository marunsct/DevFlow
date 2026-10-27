"""A compiler error passed to a fixer carries the innermost line of its explanation, which says what is wrong.

Measured on one run: the start defect said "notes-api/src/app.ts line 42: No overload matches this call." - the
first line of the compiler's error. The line that named the fault, "Type 'void' is not assignable to type
'HandlerResponse<any>'" (a handler that returned nothing), was the last of the indented lines under it and was
dropped, and the product did not start through two more sprint attempts.
"""
from __future__ import annotations

from app.stacks import compiler_errors

OUTPUT = """src/app.ts(42,22): error TS2769: No overload matches this call.
  The last overload gave the following error.
    Argument of type '(c: Context<BlankEnv, "/health", BlankInput>) => void' is not assignable to parameter of type 'H'.
      Type '(c: Context) => void' is not assignable to type 'Handler'.
        Type 'void' is not assignable to type 'HandlerResponse<any>'.
src/routes/notes.ts(9,3): error TS2304: Cannot find name 'store'.
"""


def test_the_innermost_reason_goes_with_the_error():
    found = compiler_errors.parse(OUTPUT)
    assert found[0][:3] == ("src/app.ts", 42, 2769)
    assert "No overload matches this call." in found[0][3]
    assert "Type 'void' is not assignable to type 'HandlerResponse<any>'." in found[0][3]


def test_an_error_with_no_explanation_is_as_it_was():
    found = compiler_errors.parse(OUTPUT)
    assert found[1] == ("src/routes/notes.ts", 9, 2304, "Cannot find name 'store'.")
