"""Every document this workflow writes, rendered from a fixed template.

A stage returns a structured response and the workflow writes the document a
person reads from it. The response's *content* is the model's; the document's
*shape* - its headings, their order, which sections exist, the labels inside a
record, what an empty section says - is decided here, once, in
`templates/<name>.md.j2`, and not by whichever model produced the content.

So changing the model changes what the sections say and nothing about which
sections there are or where to find them. Two runs on different models produce
documents a reader - or a parser, like the sprint panel in the UI - can read
the same way.

Before this, five of the nine documents went through a generic renderer that
turned each schema field into a heading and each nested record into whatever
its first field happened to hold, so a delegated task's heading was the first
sentence the model wrote for it. The templates name every section explicitly,
and `tests/test_document_templates.py` checks that every field of every schema
is placed in its template, so a field added to a schema cannot silently drop
out of the document.
"""

from app.doc_templates.render import TEMPLATE_DIR, render_document, template_names

__all__ = ["TEMPLATE_DIR", "render_document", "template_names"]
