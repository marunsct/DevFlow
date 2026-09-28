"""The one rule that stops a brief from outlawing its own test suite.

A brief's technical constraints describe the product the user will receive.
They do not describe the machine that builds it. Across the stored workspaces
those two were conflated, and the consequence is always the same: the testing
specialist reads "No external dependencies beyond basic HTML/CSS/JS", believes
`@playwright/test` is forbidden, and reaches for something that cannot do the
job - or for nothing at all.

run-2d9066e2 is the clearest case. Its brief forbids external dependencies, and
`TESTABILITY_RULE` mandates Playwright for browser UI. Both were read as
binding, so the sprint spent all three of its remediation attempts on the
contradiction and the run failed without a single product defect in it. The
constraint was never aimed at the test suite; nothing in the brief said it was,
and nothing in the pipeline said it was not.

run-551640d3 failed from the other side of the same rule. It installed `jsdom`
to give its tests a DOM and recorded the decision as a *risk* - "Potential need
for jsdom to mock DOM in tests, which would introduce an external dependency" -
because the constraint it was reading did not distinguish the product's
dependencies from its own. The instinct was right and the reading was wrong,
and the run treated a correct decision as a liability.

The distinction this module draws is not subtle and it is not new; it is the
one every package manager in every ecosystem already takes for granted. Node
splits `dependencies` from `devDependencies`; Maven and Gradle have `test`
scope; Cargo has `[dev-dependencies]`; Composer has `require-dev`; Ruby has
`group :test`; .NET marks a test-only `PackageReference` with `PrivateAssets`;
Python puts test tooling in dependency groups or dev extras; Go's tests are
part of the module and install nothing. A constraint on the first says nothing
about the second, and a reviewer that cannot see the difference will block the
only suite that can test the product.

Nothing here relaxes the constraint on the product. A brief that forbids
dependencies still gets a product with none, and
`what_the_brief_forbids_that_is_there` still reports every runtime dependency
it finds. What changes is that the same check no longer treats a test-scoped
dependency as a violation of it.
"""

from __future__ import annotations

#: The rule itself, in the voice of the other agent rules. Embedded in every
#: prompt that chooses a stack, writes a specification, reviews one, builds the
#: product or tests it - because the contradiction it resolves can be walked
#: into from any of those, and each one needs to recognise it in the work of
#: the stages before it. Written stack-agnostically: the examples span the
#: ecosystems this harness builds in, because a rule that only names npm is a
#: rule a Python, Go or Java run will ignore.
TESTING_DEPENDENCY_RULE = """Testing is exempt from the product's dependency constraints:
- A CONSTRAINT ON THE PRODUCT'S DEPENDENCIES IS NOT A CONSTRAINT ON ITS TESTS.
  "No external dependencies", "no frameworks", "no build step", "no third-party
  packages" and "maximum N lines of code" describe what the user receives. They
  do not describe the developer's machine, and they never forbid a test runner,
  a browser binary, a mocking library or a coverage tool. Read every such
  constraint as applying to what is SHIPPED.
- YOU MUST NOT ACCEPT "we cannot test this because the brief forbids
  dependencies". That answer is always wrong, in every language and stack. A
  test suite that needs a package installs it in the ecosystem's test-only
  scope, which ships to nobody, costs the user nothing and breaks no constraint
  in the brief. The stack's own guidance, appended under FRAMEWORK
  CAPABILITIES, names that scope for its language. If a constraint appears to
  rule out testing, the constraint has been read as covering something it does
  not.
- A TEST FRAMEWORK IS CHOSEN FOR WHAT IT CAN VERIFY, NOT FOR WHAT IT INSTALLS.
  A user interface is verified by driving the real interface, and a brief
  forbidding dependencies does not make a mock of its rendering layer adequate;
  it never makes "manual testing" or "no test framework" an answer. The stack's
  own guidance names the framework for its language and interface.
- THE USER MAY CHOOSE A TESTING STACK. A request for a specific test framework
  or tool is honoured as given, and it is not overruled by a dependency
  constraint in the brief. The two are not in conflict: one is about the
  product, the other about how it is verified.
- NEVER DELETE, DISABLE OR AVOID PRODUCT CODE TO SATISFY A TEST TOOL. If a test
  environment cannot support a feature, fix the environment or substitute the
  boundary - do not remove the thing being tested.
- IF YOU ARE REVIEWING: a specification, stack or plan that declines to test -
  or that picks an inadequate test approach - because of a dependency
  constraint is a BLOCKING finding. Name the constraint and state that it
  governs the shipped product only. The same holds for a decision recorded as a
  risk for installing a test-only dependency: that is the constraint being
  applied to the wrong thing, and it is not a risk.
- IF YOU ARE BUILDING OR TESTING: install what the suite needs, in the
  ecosystem's test-only scope, and say so plainly. Do not ask permission from a
  constraint that does not apply, and do not record the install as a risk."""

__all__ = ["TESTING_DEPENDENCY_RULE"]
