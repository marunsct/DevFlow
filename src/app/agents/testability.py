"""The one design rule that decides whether a headless test suite is cheap.

There is no browser in this sandbox, which every prompt already says. What no
prompt said is the consequence: a module that touches `document` while it is
being loaded cannot be imported by a test at all, so testing any part of it
means reconstructing a DOM first.

Measured across four runs of the same brief. The app entry point called
`document.getElementById(...)` and `form.addEventListener(...)` at the top
level, so on  


 Its technical
specification said, in as many words, "No module system (no ES modules, no
CommonJS) - single global scope", and two lines later "Tests run with a single
command: node --test tests/". Those cannot both hold: a runner can only test
what it can import. Seven test files then reimplemented the application rather
than import it, 169 assertions passed against a copy, and three milestone
reviews accepted it. The specialists were not careless - they were building to
a specification that had already ruled testing out, to honour a "no external
dependencies" constraint that native modules never breached.

html` - "No external files, no build step, no module system". Getting
the shape right does not help if nothing can open the file.

 Its
specification asked for ES modules and a guarded bootstrap; its `app.js`
delivered both - `export { logic, storage, ui }` under
`if (typeof document !== "undefined") init();`. No `package.json` declared the
module type, so `node --test` loaded the file as CommonJS, the exports were
invisible, and the testing specialist wrote "we can't directly import app.js",
copied the logic, and passed. Every part correct except the one line that tells
the runtime what kind of file it is reading.

 With this
rule in force the application came back correctly shaped - pure functions
taking their arguments, a storage adapter, every DOM reference inside `init()`.
But `init()` was still called bare at module scope and nothing was exported, so
the module still could not be imported, and the testing specialist wrote:
"it cannot be directly imported in a headless Node environment. Instead, this
test file defines the same pure logic functions inline." Six tests passed
against a copy of the code. `analysis.integration_checks` now detects that.

 `script.js` exported eight functions under a guarded bootstrap, a
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
- The thing that breaks a headless test is a module that reads or writes the DOM
  while it is being loaded. It reaches for `document`, `window` or `localStorage`
  at module scope, so the import itself runs that code and throws before any of
  your assertions are reached - and the only fix left to the test is to skip the
  import and copy the code, which tests nothing.
- FOR FRONTEND WEB UI CODE ONLY: YOU MUST USE Playwright (`@playwright/test`) to verify DOM interactions and application logic end-to-end. Do NOT use jsdom or Node-based DOM mocks, as they cause false positives and break the real UI. To test DOM logic, write Playwright tests that interact with the real browser. Install it using `npm i -D @playwright/test` and `npx playwright install chromium`. Run it with `npx playwright test`, and use a BUILT-IN reporter - `--reporter=line` or `--reporter=list`. Do NOT pass `--reporter=tap`: Playwright resolves that name to an npm package called `tap`, which is not installed, and the whole suite dies with "Cannot find module 'tap'" before a single test runs.
- A PLAYWRIGHT TEST CANNOT OPEN THE PAGE WITH `file://`. Chromium blocks an ES
  module script loaded from a `file://` URL on CORS grounds - "Cross origin
  requests are only supported for protocol schemes: ... http, https" - so the
  page loads, the script never runs, and the test times out waiting for a
  global the module never set. The page is not broken and neither is the test;
  the URL scheme is. addTask` over `file://` and failed on every run of it.  Load the page over `http://localhost:<port>` instead, and let Playwright
  manage the server itself - declare a `webServer` in `playwright.config.ts`
  and it starts the server, runs the suite, and stops it again, all inside the
  one `npx playwright test` command that terminates on its own:
      webServer: {
        command: 'npx serve .',       // or `node server.mjs`
        url: 'http://localhost:3000',
        reuseExistingServer: false,
      }
  Do NOT run a static server as a command of its own - it never exits, it is
  refused, and nothing connects to it. A page that must also work when opened
  directly from the filesystem is a separate requirement; it is not tested by
  a `file://` Playwright test that cannot load it.
- FOR ALL OTHER LANGUAGES/STACKS (Python, Go, Java, CLI apps, backend, etc): Use the testing framework appropriate to the language (e.g., PyTest, Go test, JUnit). Ensure tests are runnable and output results clearly.
- NEVER remove or disable core application logic (including UI logic) to satisfy a test framework's limitations (e.g., headless test errors). If a test environment cannot support a feature, fix the test environment or mock appropriately, rather than deleting the code under test.
- ALWAYS compare the output files against requirements and logs. Ensure that no previously working features were silently dropped.
- Keep the pure logic apart from I/O or DOM wiring. Put state and rules in functions that take their input as
  arguments and return a value. Export them for unit testing.
- Do the DOM wiring in one `init()` (or `main()`) that the page calls. Guard
  the call so importing the file does not run it:
      if (typeof document !== 'undefined') init();
  A bare `init();` at the end of the file is the whole problem - the import
  itself touches the DOM and throws before a test reaches anything.
- EXPORT the pure functions. A test that cannot import them will copy them
  instead, and a copy passes whatever your code does. If you find yourself
  writing "this test defines the same logic inline", stop: that test proves
  nothing, and it will be rejected.
- CALL THE FUNCTION YOU IMPORTED. This defect survives importing. A test that
  imports the module and then asserts `typeof mod.addTask === 'function'` has
  checked that an export exists, which is not testing it; if the assertions
  about what the function DOES run against a `function addTask` declared in the
  test file, they still pass whatever your code does. When a name appears both
  as an import and as your own declaration of the same name, the tests are
  calling yours. Import it once, call that, and declare nothing of that name.
- "IT DID NOT THROW" IS NOT A RESULT. `assert.doesNotThrow(() => saveTasks(x))`
  passes whether the function saves anything or nothing at all; so does a test
  that only checks `typeof`. Assert on what the function RETURNED, or on the
  state it changed - read it back and compare.  Persistence was an acceptance
  criterion of that brief.
- THE TEST FOR THIS: if you replaced the body of the function with
  `return <its first argument>`, would any test fail? If not, that function is
  not tested, however many tests name it.
- IF A FUNCTION IS AWKWARD TO CALL, CHANGE THE FUNCTION, NOT THE TEST. "The
  browser's random ids may differ, so I re-implemented it here" is not a reason
  to copy - it is a reason to take the id generator as an argument, or to
  assert on the shape of what comes back rather than the exact value. Copying
  turns an awkward design into a suite that proves nothing, and the awkward
  design ships unchanged.
- THE LOGIC MUST LIVE IN A FILE A TEST CAN OPEN. JavaScript inside a
  `<script>` tag in your HTML is unreachable: no runner can import it, so the
  only way to test it is to copy it, and a copy passes whatever your code does.
  One `app.js` beside `index.html` costs nothing - it is still a single-page
  application, still no build step, still no dependency - and it is the whole
  difference between a suite that tests the product and one that tests itself.
- IF YOU USE `export`, DECLARE IT. A `.js` file is CommonJS unless something
  says otherwise, so a test importing it gets "does not provide an export
  named ..." and the exports are invisible - the code looks importable and is
  not. Ship a `package.json` containing `{"type": "module"}` beside it, or name
  the files `.mjs`. Neither installs anything.
- THE SAME `package.json` MUST SAY HOW TO RUN THE TESTS. If you are writing one
  at all and the project has tests, give it
  `"scripts": {"test": "node --test <your test files>"}`. Without it `npm test`
  answers "missing script: test", so the suite is reachable only by someone who
  already knows the command - and to anyone else the project reads as having no
  tests. Measured across the delivered workspaces: five of the nine that ship a
  manifest alongside tests have no way to run them by the obvious command.
- WHERE THE PRODUCT RUNS IS NOT WHERE THE TESTS RUN. A page that ships as
  static files and runs in a browser is still tested with `node --test` on the
  machine that builds it. "Static-only deployment, so no Node runtime, so no
  automated tests" is three steps of correct reasoning ending somewhere false:
  the runtime the tests need is the developer's, and it is already here.
   Deployment
  constrains what you SHIP. It does not constrain what you can RUN while
  building it.
- A MODULE SYSTEM IS NOT AN EXTERNAL DEPENDENCY. `export` and
  `<script type="module">` are part of the browser and part of Node; they
  install nothing and add no package. A brief that forbids external
  dependencies does not forbid them. Choosing "no module system, single global
  scope" to honour such a constraint gives up every real test in exchange for
  nothing, because a test runner can only test what it can import.
- Reach storage through a small adapter passed in as an argument, so a test can
  hand it a plain object instead of mocking a browser API. The same holds for a
  database: nothing is running here, so code that talks to PostgreSQL directly
  is code no test can execute. Put the queries behind an adapter and let the
  tests substitute it.
- The test for a rule then imports the function and calls it. Only the wiring
  needs a DOM, and a thin wiring layer is worth far less test effort than the
  rules are."""

__all__ = ["TESTABILITY_RULE"]
