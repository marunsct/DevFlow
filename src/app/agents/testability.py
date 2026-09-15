"""The one design rule that decides whether a headless test suite is cheap.

There is no browser in this sandbox, which every prompt already says. What no
prompt said is the consequence: a module that touches `document` while it is
being loaded cannot be imported by a test at all, so testing any part of it
means reconstructing a DOM first.

Measured across four runs of the same brief. The app entry point called
`document.getElementById(...)` and `form.addEventListener(...)` at the top
level, so on run-61c5a5b6 the testing specialist loaded it through `node:vm`
with a hand-written DOM: five rewrites of the test file to get
`addEventListener`, then `classList`, then element identity right, and a
defect-fix round afterwards. run-304add54 failed outright on the same problem.
run-cbd22a34 paid for it in dependencies instead - vitest and jsdom took the
workspace from 46 MB to 221 MB against a brief that asked for none.

run-2b5def74 traced it to the decision that causes it. Its technical
specification said, in as many words, "No module system (no ES modules, no
CommonJS) - single global scope", and two lines later "Tests run with a single
command: node --test tests/". Those cannot both hold: a runner can only test
what it can import. Seven test files then reimplemented the application rather
than import it, 169 assertions passed against a copy, and three milestone
reviews accepted it. The specialists were not careless - they were building to
a specification that had already ruled testing out, to honour a "no external
dependencies" constraint that native modules never breached.

run-2f252e4e reached the same dead end from the other direction, one run
later, with the structural half of this rule already in force: its
specification correctly described pure functions, a storage adapter and an
`init()`, and then put all of it inside a `<script>` tag in a single
`index.html` - "No external files, no build step, no module system". Getting
the shape right does not help if nothing can open the file.

run-2b5def74 also shows why the second half matters as much as the first. With this
rule in force the application came back correctly shaped - pure functions
taking their arguments, a storage adapter, every DOM reference inside `init()`.
But `init()` was still called bare at module scope and nothing was exported, so
the module still could not be imported, and the testing specialist wrote:
"it cannot be directly imported in a headless Node environment. Instead, this
test file defines the same pure logic functions inline." Six tests passed
against a copy of the code. `analysis.integration_checks` now detects that.

Nothing in the product needed to be that way. The logic under test - create a
task, toggle it, filter the list - is pure. Only the wiring needs a document,
and wiring is the part a test does not need to load.
"""

TESTABILITY_RULE = """Testability - this decides whether the tests can run at all:
- There is no browser here. A module that reads or writes the DOM while it is
  being loaded cannot be imported by a headless test, so testing one pure
  function inside it means faking a whole document first.
- Keep the two apart. Put state and rules in functions that take their input as
  arguments and return a value - no `document`, no `window`, no `localStorage`
  reached for directly. Export them.
- Do the DOM wiring in one `init()` (or `main()`) that the page calls. Guard
  the call so importing the file does not run it:
      if (typeof document !== 'undefined') init();
  A bare `init();` at the end of the file is the whole problem - the import
  itself touches the DOM and throws before a test reaches anything.
- EXPORT the pure functions. A test that cannot import them will copy them
  instead, and a copy passes whatever your code does. If you find yourself
  writing "this test defines the same logic inline", stop: that test proves
  nothing, and it will be rejected.
- THE LOGIC MUST LIVE IN A FILE A TEST CAN OPEN. JavaScript inside a
  `<script>` tag in your HTML is unreachable: no runner can import it, so the
  only way to test it is to copy it, and a copy passes whatever your code does.
  One `app.js` beside `index.html` costs nothing - it is still a single-page
  application, still no build step, still no dependency - and it is the whole
  difference between a suite that tests the product and one that tests itself.
- A MODULE SYSTEM IS NOT AN EXTERNAL DEPENDENCY. `export` and
  `<script type="module">` are part of the browser and part of Node; they
  install nothing and add no package. A brief that forbids external
  dependencies does not forbid them. Choosing "no module system, single global
  scope" to honour such a constraint gives up every real test in exchange for
  nothing, because a test runner can only test what it can import.
- Reach storage through a small adapter passed in as an argument, so a test can
  hand it a plain object instead of mocking a browser API.
- The test for a rule then imports the function and calls it. Only the wiring
  needs a DOM, and a thin wiring layer is worth far less test effort than the
  rules are."""

__all__ = ["TESTABILITY_RULE"]
