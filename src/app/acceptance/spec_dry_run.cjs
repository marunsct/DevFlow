'use strict';
// The dry run of a locked suite (`spec_dry_run.py`): each spec runs with the runner, `request`, `page`, `fetch` and child
// processes replaced by stand-ins, and an error the spec's own code raises is written to the report.
//
//   node spec_dry_run.cjs <suite directory> <report.json> <spec>...
//
// A stand-in answers everything and every assertion passes, so nothing the product would decide can fail here: what
// is left is what no product can change. Runs on a copy of the suite.
const Module = require('node:module');
const path = require('node:path');
const fs = require('node:fs');
const EventEmitter = require('node:events');
const childProcess = require('node:child_process');

const [suiteDir, reportFile, ...specs] = process.argv.slice(2);
const PER_TEST_MS = 3000;
const report = { files: 0, tests: 0, findings: [], inconclusive: [] };
const saveReport = () => fs.writeFileSync(reportFile, JSON.stringify(report));

// --- stand-ins ---------------------------------------------------------------------------------------------------
const pending = [];
const STUB = Symbol('stub');

function anything(runsCallbacks) {
  const children = new Map();
  const own = new Map();
  const target = () => {};
  const proxy = new Proxy(target, {
    get(_, key) {
      if (key === STUB) return true;
      if (key === 'then' || key === 'catch' || key === 'finally') return undefined;
      if (key === Symbol.toPrimitive) return (hint) => (hint === 'number' ? 1 : 'stub');
      if (key === 'toJSON') return () => 'stub';
      if (key === Symbol.iterator) return function* () { yield anything(runsCallbacks); };
      if (key === Symbol.asyncIterator) return async function* () { yield anything(runsCallbacks); };
      if (typeof key === 'symbol') return undefined;
      if (own.has(key)) return own.get(key);
      if (key === 'length' || key === 'size') return 1;
      if (!children.has(key)) children.set(key, anything(runsCallbacks));
      return children.get(key);
    },
    set(_, key, value) { own.set(key, value); return true; },
    has() { return true; },
    apply(_, __, args) {
      if (runsCallbacks) {
        for (const arg of args) {
          if (typeof arg === 'function' && !arg[STUB]) {
            const value = arg(anything(true), anything(true));
            if (value && typeof value.then === 'function') pending.push(value);
          }
        }
      }
      return anything(runsCallbacks);
    },
    construct() { return anything(runsCallbacks); },
  });
  return proxy;
}
// Data: a callback given to it runs, as `.map(...)` would run it. A page: a callback runs in the browser, not here.
const data = () => anything(true);
const browserSide = () => anything(false);

const responseMethods = new WeakSet();
function playwrightResponse() {
  const response = {
    status: () => 200, ok: () => true, statusText: () => 'OK', url: () => 'http://stub.invalid/',
    json: async () => data(), text: async () => data(), body: async () => Buffer.from(''),
    headers: () => data(), headersArray: () => [], dispose: async () => {},
  };
  for (const value of Object.values(response)) responseMethods.add(value);
  return response;
}
function requestFixture() {
  const send = async () => playwrightResponse();
  return {
    get: send, post: send, put: send, patch: send, delete: send, head: send, fetch: send,
    storageState: async () => data(), dispose: async () => {},
  };
}
globalThis.fetch = async () => ({
  status: 200, ok: true, statusText: 'OK', url: 'http://stub.invalid/', redirected: false, type: 'basic',
  headers: new Headers(), body: null, bodyUsed: false,
  json: async () => data(), text: async () => data(), arrayBuffer: async () => new ArrayBuffer(0), blob: async () => data(),
  formData: async () => data(), clone() { return this; },
});

// --- child processes and time: nothing starts, nothing waits -------------------------------------------------------
function fakeChild() {
  const child = new EventEmitter();
  // Above any pid the kernel gives (at most 2^22), should a signal ever reach the system with it.
  Object.assign(child, { pid: 2 ** 30, exitCode: null, signalCode: null, killed: false, connected: false,
    stdout: new EventEmitter(), stderr: new EventEmitter(), stdin: new EventEmitter() });
  child.stdout.setEncoding = child.stderr.setEncoding = () => {};
  child.stdin.write = child.stdin.end = () => true;
  child.unref = child.ref = child.disconnect = () => {};
  child.kill = () => {
    child.killed = true; child.exitCode = 0;
    setImmediate(() => { child.emit('exit', 0, null); child.emit('close', 0, null); });
    return true;
  };
  return child;
}
childProcess.spawn = childProcess.fork = childProcess.exec = childProcess.execFile = () => fakeChild();
childProcess.spawnSync = () => ({ status: 0, signal: null, stdout: '', stderr: '', output: [] });
childProcess.execSync = childProcess.execFileSync = () => '';
const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms, ...rest) => realSetTimeout(fn, Math.min(Number(ms) || 0, 1), ...rest);
// A spec stops the service it started by signalling its process group: `process.kill(-child.pid, 'SIGTERM')`. Nothing it
// names here is real, so no signal leaves this process. With a stand-in pid of 1 that call was kill(-1): it signalled
// every process of the user and took the machine's session down twice.
process.kill = () => true;
process._kill = () => 0;
const reallyExit = process.exit.bind(process);
process.exit = () => { throw new Error('process.exit called'); };
process.on('unhandledRejection', () => {});
process.on('uncaughtException', () => {});

// --- whose fault an error is ---------------------------------------------------------------------------------------
class OwnFault extends Error {}
const OWN_TYPE_ERRORS = /is not a function|is not a constructor|is not iterable|Cannot read properties of undefined|Cannot set properties of undefined|Assignment to constant variable/;
const inSuite = (file) => file.startsWith(suiteDir + path.sep);

function topFrame(error) {
  for (const line of String(error && error.stack || '').split('\n').slice(1)) {
    const match = line.match(/\(?((?:\/|[A-Za-z]:\\)[^():]+):(\d+):\d+\)?\s*$/);
    if (match) return { file: match[1], line: Number(match[2]) };
    if (/\bat\b.*(node:|<anonymous>)/.test(line)) return { file: '', line: 0 };
  }
  return { file: '', line: 0 };
}
function isOwn(error) {
  if (error instanceof OwnFault) return true;
  if (!(error instanceof ReferenceError || (error instanceof TypeError && OWN_TYPE_ERRORS.test(error.message)))) return false;
  return inSuite(topFrame(error).file);
}
function note(error, file, test) {
  const message = String(error && error.message || error).split('\n')[0].slice(0, 300);
  if (isOwn(error)) {
    const frame = topFrame(error);
    const where = inSuite(frame.file) ? frame : { file, line: 0 };
    const finding = { file: path.relative(suiteDir, where.file), line: where.line, test, error: `${error.name}: ${message}` };
    if (!report.findings.some((f) => f.file === finding.file && f.line === finding.line && f.error === finding.error)) {
      report.findings.push(finding);
    }
  } else {
    report.inconclusive.push({ file: path.relative(suiteDir, file), test, error: `${error && error.name}: ${message}` });
  }
  saveReport();
}

// --- expect --------------------------------------------------------------------------------------------------------
const MATCHERS = new Set(`toBe toBeCloseTo toBeDefined toBeFalsy toBeGreaterThan toBeGreaterThanOrEqual toBeInstanceOf
  toBeLessThan toBeLessThanOrEqual toBeNaN toBeNull toBeTruthy toBeUndefined toContain toContainEqual toEqual toHaveLength
  toHaveProperty toMatch toMatchObject toStrictEqual toThrow toThrowError toBeAttached toBeChecked toBeDisabled toBeEditable
  toBeEmpty toBeEnabled toBeFocused toBeHidden toBeInViewport toBeVisible toContainText toContainClass toHaveAccessibleDescription
  toHaveAccessibleErrorMessage toHaveAccessibleName toHaveAttribute toHaveClass toHaveCount toHaveCSS toHaveId toHaveJSProperty
  toHaveRole toHaveScreenshot toHaveText toHaveValue toHaveValues toHaveTitle toHaveURL toBeOK toPass toMatchSnapshot
  toMatchAriaSnapshot`.split(/\s+/));
const COMPARES = new Set(['toBe', 'toEqual', 'toStrictEqual', 'toBeGreaterThan', 'toBeLessThan', 'toBeGreaterThanOrEqual', 'toBeLessThanOrEqual']);
function matchers(actual, extra) {
  const chain = new Proxy({}, {
    get(_, name) {
      if (name === 'then') return undefined;
      if (name === 'not' || name === 'resolves' || name === 'rejects') return chain;
      if (typeof name !== 'string' || !(MATCHERS.has(name) || extra.has(name))) return undefined;
      // Thrown as it is called, as a real assertion on a value is: one written without `await` still stops its test.
      return () => {
        if (typeof actual === 'function' && responseMethods.has(actual) && COMPARES.has(name)) {
          throw new OwnFault(`${name}(...) compares the response's method itself, not what calling it returns: write it with ()`);
        }
        if (name === 'toPass' && typeof actual === 'function' && !actual[STUB]) return Promise.resolve().then(actual);
        return Promise.resolve();
      };
    },
  });
  return chain;
}
const extraMatchers = new Set();
function expect(actual) { return matchers(actual, extraMatchers); }
expect.soft = expect;
expect.poll = (fn) => {
  if (typeof fn === 'function') pending.push(Promise.resolve().then(fn));
  return matchers(undefined, extraMatchers);
};
expect.extend = (defs) => { for (const key of Object.keys(defs || {})) extraMatchers.add(key); return expect; };
expect.configure = () => expect;
for (const key of ['any', 'anything', 'arrayContaining', 'closeTo', 'objectContaining', 'stringContaining', 'stringMatching']) {
  expect[key] = () => data();
}

// --- the runner ----------------------------------------------------------------------------------------------------
let scope = null;
function newScope(parent) { return { parent, beforeAll: [], afterAll: [], beforeEach: [], afterEach: [], items: [], fixtures: parent ? parent.fixtures : {} }; }
function makeTest(fixtures) {
  const body = (title, ...rest) => { const fn = rest[rest.length - 1]; if (typeof fn === 'function') scope.items.push({ title: String(title), fn, fixtures }); };
  const skipper = (...args) => { const fn = args[args.length - 1]; if (typeof args[0] === 'string' && typeof fn === 'function') return; };
  body.only = body;
  body.skip = skipper; body.fixme = skipper; body.fail = body; body.slow = () => {}; body.setTimeout = () => {};
  body.use = () => {}; body.info = () => data();
  body.step = async (_, fn) => fn(data());
  const describe = (title, ...rest) => {
    const fn = rest[rest.length - 1];
    if (typeof fn !== 'function') return;
    const inner = newScope(scope);
    scope.items.push({ scope: inner, title: String(title) });
    const outer = scope;
    scope = inner;
    try { fn(); } finally { scope = outer; }
  };
  describe.only = describe; describe.parallel = describe; describe.serial = describe;
  describe.configure = () => {};
  describe.skip = () => {}; describe.fixme = () => {};
  describe.parallel.only = describe; describe.serial.only = describe;
  body.describe = describe;
  for (const hook of ['beforeAll', 'afterAll', 'beforeEach', 'afterEach']) {
    body[hook] = (...rest) => { const fn = rest[rest.length - 1]; if (typeof fn === 'function') scope[hook].push({ fn, fixtures }); };
  }
  body.extend = (more) => makeTest({ ...fixtures, ...more });
  return body;
}

function builtIn(name) {
  if (name === 'request') return requestFixture();
  if (name === 'baseURL') return 'http://stub.invalid';
  if (name === 'browserName') return 'chromium';
  return browserSide();
}
function namesAskedFor(fn) {
  const match = Function.prototype.toString.call(fn).match(/^(?:async\s*)?(?:function\s*\w*\s*)?\(\s*\{([^}]*)\}/);
  if (!match) return [];
  return match[1].split(',').map((part) => part.split(':')[0].split('=')[0].trim()).filter(Boolean);
}
async function withFixtures(fn, defs, made, run) {
  const names = namesAskedFor(fn);
  const step = async (index) => {
    if (index === names.length) {
      const args = new Proxy(made, { get: (_, key) => (typeof key === 'string' && !(key in made) ? builtIn(key) : made[key]) });
      return run(args);
    }
    const name = names[index];
    if (name in made) return step(index + 1);
    let def = defs[name];
    if (Array.isArray(def)) def = def[0];
    if (typeof def !== 'function') {
      made[name] = name in defs ? def : builtIn(name);
      return step(index + 1);
    }
    return withFixtures(def, defs, made, async (args) => {
      let used = false;
      let result;
      await def(args, async (value) => { used = true; made[name] = value; result = await step(index + 1); }, data());
      if (!used) { made[name] = data(); result = await step(index + 1); }
      return result;
    });
  };
  return step(0);
}
function limited(promise, label) {
  let timer;
  const limit = new Promise((_, reject) => { timer = realSetTimeout(() => reject(new Error(`${label} did not finish`)), PER_TEST_MS); });
  return Promise.race([promise, limit]).finally(() => clearTimeout(timer));
}
async function runOne(fn, fixtures, label, file, made = {}) {
  try {
    await limited(withFixtures(fn, fixtures, made, (args) => fn(args, data())), label);
    const settled = await limited(Promise.allSettled(pending.splice(0)), label);
    for (const outcome of settled) if (outcome.status === 'rejected') note(outcome.reason, file, label);
    return true;
  } catch (error) {
    pending.splice(0);
    note(error, file, label);
    return false;
  }
}
function chain(node, key) { return node ? [...chain(node.parent, key), ...node[key]] : []; }
async function runScope(node, file) {
  for (const hook of node.beforeAll) await runOne(hook.fn, hook.fixtures, 'beforeAll', file);
  for (const item of node.items) {
    if (item.scope) { await runScope(item.scope, file); continue; }
    report.tests += 1;
    const made = {};
    let ready = true;
    for (const hook of chain(node, 'beforeEach')) ready = (await runOne(hook.fn, hook.fixtures, item.title, file, made)) && ready;
    if (ready) await runOne(item.fn, item.fixtures, item.title, file, made);
    for (const hook of chain(node, 'afterEach').reverse()) await runOne(hook.fn, hook.fixtures, item.title, file, made);
  }
  for (const hook of node.afterAll) await runOne(hook.fn, hook.fixtures, 'afterAll', file);
}

// --- loading: Playwright compiles a spec, so `import` and `require` may share a file; the same is done here ---------
const test = makeTest({});
const stubModule = {
  test, expect, devices: data(), chromium: browserSide(), firefox: browserSide(), webkit: browserSide(),
  request: { newContext: async () => requestFixture() }, defineConfig: (config) => config, selectors: browserSide(),
};
stubModule.default = stubModule;

function keepLines(original, replacement) {
  return replacement + '\n'.repeat((original.match(/\n/g) || []).length);
}
function renamed(list) {
  return list.split(',').map((part) => part.trim()).filter((part) => part && !part.startsWith('type '))
    .map((part) => part.replace(/\s+as\s+/, ': ')).join(', ');
}
function compiled(source) {
  const exported = [];
  let out = source
    .replace(/^[ \t]*import\s+type\s[\s\S]*?from\s*['"][^'"]+['"];?/gm, (all) => keepLines(all, ''))
    .replace(/^[ \t]*import\s+([\w$]+)?\s*,?\s*(?:\*\s+as\s+([\w$]+))?\s*(?:\{([^}]*)\})?\s*from\s*(['"][^'"]+['"]);?/gm,
      (all, name, star, list, from) => {
        const parts = [];
        if (name) parts.push(`const ${name} = __default(require(${from}));`);
        if (star) parts.push(`const ${star} = require(${from});`);
        if (list !== undefined && renamed(list)) parts.push(`const { ${renamed(list)} } = require(${from});`);
        return keepLines(all, parts.join(' '));
      })
    .replace(/^[ \t]*import\s+(['"][^'"]+['"]);?/gm, (all, from) => keepLines(all, `require(${from});`))
    .replace(/\bimport\.meta\.url\b/g, "require('node:url').pathToFileURL(__filename).href")
    .replace(/\bimport\.meta\.dirname\b/g, '__dirname')
    .replace(/\bimport\.meta\.filename\b/g, '__filename')
    .replace(/^[ \t]*export\s+default\s+/gm, 'exports.default = ')
    .replace(/^[ \t]*export\s+\{([^}]*)\}(?:\s*from\s*(['"][^'"]+['"]))?;?/gm, (all, list, from) => {
      const pairs = list.split(',').map((p) => p.trim()).filter(Boolean).map((p) => p.split(/\s+as\s+/));
      const body = pairs.map(([a, b]) => `exports.${b || a} = ${from ? `require(${from}).${a}` : a};`).join(' ');
      return keepLines(all, from ? body : (exported.push(body), ''));
    })
    .replace(/^([ \t]*)export\s+((?:async\s+)?function\*?\s+([\w$]+)|class\s+([\w$]+))/gm, (all, indent, rest, fn, cls) => {
      exported.push(`exports.${fn || cls} = ${fn || cls};`);
      return indent + rest;
    })
    .replace(/^([ \t]*)export\s+(?:const|let|var)\s+([\w$]+)/gm, (all, indent, name) => {
      exported.push(`exports.${name} = ${name};`);
      return all.replace(/export\s+/, '');
    });
  out = `const __default = (m) => (m && m.__esModule === undefined && m.default !== undefined ? m.default : m);${out}\n${exported.join(' ')}`;
  return out;
}

const loadRequest = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === '@playwright/test' || request === 'playwright/test') return stubModule;
  try {
    return loadRequest.call(this, request, parent, isMain);
  } catch (error) {
    // The product's files and third-party packages are not in the copy: what they export is the product's to answer.
    if (error && error.code === 'MODULE_NOT_FOUND') return data();
    throw error;
  }
};
const compileFrom = (module, filename, strip) => {
  let source = fs.readFileSync(filename, 'utf8');
  if (strip) source = Module.stripTypeScriptTypes(source, { mode: 'strip' });
  module._compile(compiled(source), filename);
};
for (const extension of ['.js', '.mjs', '.cjs']) Module._extensions[extension] = (m, f) => compileFrom(m, f, false);
for (const extension of ['.ts', '.mts', '.cts']) Module._extensions[extension] = (m, f) => compileFrom(m, f, true);

(async () => {
  process.removeAllListeners('warning');
  process.on('warning', () => {});
  for (const relative of specs) {
    const file = path.join(suiteDir, relative);
    scope = newScope(null);
    report.files += 1;
    const top = scope;
    try {
      require(file);
    } catch (error) {
      if (error instanceof SyntaxError) report.inconclusive.push({ file: relative, test: '(loading)', error: `SyntaxError: ${error.message}` });
      else note(error, file, '(loading)');
      continue;
    }
    await runScope(top, file);
    saveReport();
  }
  saveReport();
  reallyExit(0);
})();
