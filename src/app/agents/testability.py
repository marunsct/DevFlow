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
- The thing that breaks a headless test is a module that does its I/O while it
  is being loaded - it touches a page, a database, the network or the file
  system at the top level - so the import itself runs that code and fails
  before any of your assertions are reached, and the only fix left to the test
  is to skip the import and copy the code, which tests nothing.
- Use the test tooling the stack's own guidance names. It is appended to these
  instructions under FRAMEWORK CAPABILITIES when the stack has any: which runner
  ships with the language, where a test-only dependency goes, and how a user
  interface is driven. For a user interface, verify it through the real
  interface with an automated driver - a mock of the rendering layer passes
  while the real thing is broken.
- NEVER remove or disable core application logic (including UI logic) to satisfy
  a test framework's limitations. If a test environment cannot support a
  feature, fix the test environment or substitute the boundary, rather than
  deleting the code under test.
- ALWAYS compare the output files against requirements and logs. Ensure that no
  previously working features were silently dropped.
- Keep the pure logic apart from I/O and UI wiring. Put state and rules in
  functions that take their input as arguments and return a value.
- Do the wiring in one entry point (`init()`, `main()`, the framework's own)
  that the program calls, guarded so that importing the module does not run it.
- EXPORT the pure functions - make them importable in whatever way the language
  does that. A test that cannot import them will copy them instead, and a copy
  passes whatever your code does. If you find yourself writing "this test
  defines the same logic inline", stop: that test proves nothing, and it will
  be rejected.
- CALL THE FUNCTION YOU IMPORTED. A test that imports the module and then only
  checks that a name exists has not tested it; and if its assertions about what
  the function DOES run against a same-named function declared in the test
  file, they pass whatever your code does. Import it once, call that, and
  declare nothing of that name.
- "IT DID NOT THROW" IS NOT A RESULT. An assertion that a call raised no error
  passes whether the function saved anything or nothing at all; so does one that
  checks only a type. Assert on what the function RETURNED, or on the state it
  changed - read it back and compare. Observed: a save function covered only by
  such an assertion could have its whole body replaced by `return <its
  argument>` with every test still passing, and persistence was an acceptance
  criterion of that brief.
- THE TEST FOR THIS: if you replaced the body of the function with
  `return <its first argument>`, would any test fail? If not, that function is
  not tested, however many tests name it.
- IF A FUNCTION IS AWKWARD TO CALL, CHANGE THE FUNCTION, NOT THE TEST. A
  non-deterministic value (an id, a clock) is a reason to take its source as an
  argument, or to assert on the shape of what comes back - not to re-implement
  the function in the test. Copying turns an awkward design into a suite that
  proves nothing, and the awkward design ships unchanged.
- THE LOGIC MUST LIVE IN A FILE A TEST CAN OPEN. Logic embedded in markup, a
  template or a page cannot be imported by any runner, so the only way to test
  it is to copy it. A separate source file beside it costs nothing.
- WHERE THE PRODUCT RUNS IS NOT WHERE THE TESTS RUN. The runtime the tests need
  is the developer's, and it is already here. Deployment constrains what you
  SHIP; it does not constrain what you can RUN while building it.
- A MODULE SYSTEM IS NOT AN EXTERNAL DEPENDENCY. The language's own way of
  exporting and importing installs nothing and adds no package, so a brief that
  forbids external dependencies does not forbid it. Giving it up to honour such
  a constraint gives up every real test in exchange for nothing, because a test
  runner can only test what it can import.
- Reach storage through a small adapter passed in as an argument, so a test can
  hand it a plain object instead of mocking a platform API. The same holds for a
  database: nothing is running here, so code that talks to PostgreSQL directly
  is code no test can execute. Put the queries behind an adapter and let the
  tests substitute it.
- The test for a rule then imports the function and calls it. Only the wiring
  needs the real environment, and a thin wiring layer is worth far less test
  effort than the rules are.
"""

__all__ = ["TESTABILITY_RULE"]
