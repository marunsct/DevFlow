"""The one design rule that decides whether a headless test suite is cheap.

There is no browser in this sandbox, which every prompt already says. What no
prompt said is the consequence: a module that touches `document` while it is
being loaded cannot be imported by a test at all, so testing any part of it
means reconstructing a DOM first.

Measured across four runs of the same brief. The app entry point called
`document.getElementById(...)` and `form.addEventListener(...)` at the top
level, so on one run the testing specialist loaded it through `node:vm`
with a hand-written DOM: five rewrites of the test file to get
`addEventListener`, then `classList`, then element identity right, and a
defect-fix round afterwards. One run failed outright on the same problem.
One run paid for it in dependencies instead - vitest and jsdom took the
workspace from 46 MB to 221 MB against a brief that asked for none.

One run traced it to the decision that causes it. Its technical
specification said, in as many words, "No module system (no ES modules, no
CommonJS) - single global scope", and two lines later "Tests run with a single
command: node --test tests/". Those cannot both hold: a runner can only test
what it can import. Seven test files then reimplemented the application rather
than import it, 169 assertions passed against a copy, and three milestone
reviews accepted it. The specialists were not careless - they were building to
a specification that had already ruled testing out, to honour a "no external
dependencies" constraint that native modules never breached.

One run reached the same dead end from the other direction, one run
later, with the structural half of this rule already in force: its
specification correctly described pure functions, a storage adapter and an
`init()`, and then put all of it inside a `<script>` tag in a single
`index.html` - "No external files, no build step, no module system". Getting
the shape right does not help if nothing can open the file.

One run got everything else right and still could not be tested. Its
specification asked for ES modules and a guarded bootstrap; its `app.js`
delivered both - `export { logic, storage, ui }` under
`if (typeof document !== "undefined") init();`. No `package.json` declared the
module type, so `node --test` loaded the file as CommonJS, the exports were
invisible, and the testing specialist wrote "we can't directly import app.js",
copied the logic, and passed. Every part correct except the one line that tells
the runtime what kind of file it is reading.

One run also shows why the second half matters as much as the first. With this
rule in force the application came back correctly shaped - pure functions
taking their arguments, a storage adapter, every DOM reference inside `init()`.
But `init()` was still called bare at module scope and nothing was exported, so
the module still could not be imported, and the testing specialist wrote:
"it cannot be directly imported in a headless Node environment. Instead, this
test file defines the same pure logic functions inline." Six tests passed
against a copy of the code. `analysis.integration_checks` now detects that.

One run had every structural part of this rule right and copied the code
anyway. `script.js` exported eight functions under a guarded bootstrap, a
`package.json` declared `{"type": "module"}`, and `script.test.mjs` imported
the real module nine times - to assert `typeof mod.addTask === 'function'` and
nothing else. Above those, under the heading "Inline copies of the pure
functions (mirrors script.js exactly)", it redeclared all four and ran every
behavioural assertion against them. Its stated reason was that
`crypto.randomUUID()` "may not be the same as the browser's", which the test
itself disproves by importing `randomUUID` from `node:crypto`. So the
clause about "this test defines the same logic inline" was not enough: it
answers the case where importing is impossible, and this one could import.

That run is also why a rename is a poor way to check a suite is bound.
Renaming an export breaks the `typeof` checks, which reports failures and
makes the suite look connected while every assertion about behaviour still
passes against the copy. A mutation has to change what a function DOES.

Nothing in the product needed to be that way. The logic under test - create a
task, toggle it, filter the list - is pure. Only the wiring needs a document,
and wiring is the part a test does not need to load.
"""

TESTABILITY_RULE = """Testability - this decides whether the tests can run at all:
- A headless test breaks on a module that does its I/O while it is being
  loaded - touching a page, a database, the network or the file system at the
  top level - because importing it runs that code before any assertion.
- Keep the pure logic apart from I/O and UI wiring: rules and state in
  functions that take their input as arguments and return a value. Do the
  wiring in one entry point (`init()`, `main()`, the framework's own),
  guarded so that importing the module does not run it.
- THE LOGIC MUST LIVE IN A FILE A TEST CAN OPEN. Logic embedded in markup, a
  template or a page cannot be imported by any runner.
- EXPORT the pure functions, in whatever way the language does. A test that
  cannot import them copies them, and a copy passes whatever your code does.
- CALL THE FUNCTION YOU IMPORTED. A test that only checks that a name exists
  has not tested it; declare nothing in the test with the same name.
- IT DID NOT THROW IS NOT A RESULT. Assert on what the function returned, or
  read back the state it changed. The check: if its body were replaced by
  `return <its first argument>`, would any test fail?
- IF A FUNCTION IS AWKWARD TO CALL, CHANGE THE FUNCTION, NOT THE TEST: take a
  clock or an id source as an argument rather than re-implementing it.
- Reach storage and databases through a small adapter passed in as an
  argument, so a test can hand it a plain object. No database server runs
  here, so code that talks to PostgreSQL directly is code no test can execute.
- Use the test tooling the stack's own guidance names under FRAMEWORK
  CAPABILITIES. For a user interface, verify it through the real interface
  with an automated driver; a mock of the rendering layer passes while it is
  broken.
- WHERE THE PRODUCT RUNS IS NOT WHERE THE TESTS RUN. The runtime the tests
  need is the developer's, and it is already here.
- A MODULE SYSTEM IS NOT AN EXTERNAL DEPENDENCY: it installs nothing and adds
  no package, and a test runner can only test what it can import.
- NEVER remove or disable product logic to satisfy a test tool. Fix the test
  environment or substitute the boundary instead, and make sure no working
  feature was dropped.
"""

__all__ = ["TESTABILITY_RULE"]
