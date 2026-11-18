'use strict';
// The start probe in a command's own container (`start_probe.py`): starts the project's `start.sh` the way the suite
// does, polls the readiness path on 127.0.0.1:$PORT, then stops the service and prints one JSON object:
//   {"answered": <status>} | {"exited": <code>} | {"silent": true}, with "output": what the service printed.
//
//   node start_probe.cjs <readiness path> <seconds to wait> <most output>
const { spawn } = require('node:child_process');
const http = require('node:http');

const [ready, waitSeconds, mostOutput] = [process.argv[2] || '/', Number(process.argv[3] || 12), Number(process.argv[4] || 1200)];
const chunks = [];
const child = spawn('sh', ['start.sh'], { detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
child.stdout.on('data', (d) => chunks.push(d));
child.stderr.on('data', (d) => chunks.push(d));
let done = false;

function finish(result) {
  if (done) return;
  done = true;
  try { process.kill(-child.pid, 'SIGKILL'); } catch (e) { /* already gone */ }
  setTimeout(() => {
    const output = Buffer.concat(chunks).toString('utf8').trim();
    process.stdout.write(JSON.stringify({ ...result, output: output.slice(-mostOutput) }));
    process.exit(0);
  }, 200);
}

child.on('error', () => finish({ exited: 127 }));
child.on('exit', (code, signal) => {
  // As Python reports a process ended by a signal: the signal's number, negative.
  const signalled = signal ? -(require('node:os').constants.signals[signal] || 0) : -1;
  finish({ exited: code === null ? signalled : code });
});

const started = Date.now();
function poll() {
  if (done) return;
  if (Date.now() - started > waitSeconds * 1000) { finish({ silent: true }); return; }
  const request = http.get({ host: '127.0.0.1', port: Number(process.env.PORT), path: ready, timeout: 2000 }, (answer) => {
    answer.resume();
    finish({ answered: answer.statusCode });
  });
  request.on('timeout', () => request.destroy());
  request.on('error', () => setTimeout(poll, 300));
}
poll();
