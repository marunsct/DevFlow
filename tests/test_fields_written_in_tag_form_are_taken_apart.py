"""Fields the model wrote in its tag form inside another field's value are taken back apart.

Measured on one gate run: the architect wrote its specification as
`<parameter=product_scope>...</parameter></function></tool_call><tool_call>
<function=TechnicalSpecificationOutput><parameter=data_contracts>...`, the
server's parser put all 111,127 characters into `product_scope`, and the
sections after the first were lost inside it with the model's own tags.
"""
from __future__ import annotations

from app.models import tool_arguments
from app.models.tool_arguments import CUT_OFF, with_the_written_parameters_apart

SCHEMA = {"properties": {"product_scope": {"type": "string"}, "data_contracts": {"type": "array"},
                         "file_plan": {"type": "array"}}}

WRITTEN = (
    "Notes over HTTP.\n</parameter></function></tool_call><tool_call><function=TechnicalSpecificationOutput>"
    "<parameter=data_contracts>## User record</parameter><parameter=file_plan>- `src/app.ts` - routes"
)


def test_each_field_is_taken_out_by_its_tag_and_the_unclosed_one_is_cut_off():
    args = with_the_written_parameters_apart({"product_scope": WRITTEN}, SCHEMA)

    assert args["product_scope"] == "Notes over HTTP."
    assert args["data_contracts"] == "## User record"
    assert "file_plan" not in args and args[CUT_OFF] == "file_plan"
    assert all("</parameter>" not in str(v) and "<tool_call>" not in str(v) for v in args.values())


def test_a_value_with_no_tags_is_left_alone():
    plain = {"product_scope": "Notes over HTTP, kept in a store.", "file_plan": ["src/app.ts - routes"]}

    assert with_the_written_parameters_apart(plain, SCHEMA) == plain


def test_a_whole_reply_is_taken_apart_with_no_cut_off():
    written = "Notes.</parameter><parameter=data_contracts>## User</parameter>"

    args = with_the_written_parameters_apart({"product_scope": written}, SCHEMA)

    assert args == {"product_scope": "Notes.", "data_contracts": "## User"}
