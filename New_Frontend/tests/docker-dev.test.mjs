import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const launcher = fileURLToPath(new URL('../scripts/docker-dev.mjs', import.meta.url));
const temporaryRoot = resolve(tmpdir(), 'transformers-frontend-dev-tests');

// Use real launcher/child processes but intercept npm, so these tests neither
// install packages nor depend on a shell executable working the same on Windows.
function fixture(t) {
  mkdirSync(temporaryRoot, { recursive: true });
  const root = mkdtempSync(join(temporaryRoot, 'run-'));
  t.after(() => {
    assert.ok(resolve(root).startsWith(`${temporaryRoot}${sep}`));
    rmSync(root, { recursive: true, force: true });
  });
  const nextBin = join(root, 'node_modules/next/dist/bin/next');
  const marker = join(root, 'node_modules/.docker-dev-dependencies');
  const fakeNext = `
    console.log(JSON.stringify(process.argv.slice(2)));
    if (process.env.LAUNCHER_TEST_WAIT === '1') {
      console.log('NEXT_READY');
      setInterval(() => {}, 1000);
    } else {
      process.exit(Number(process.env.LAUNCHER_TEST_NEXT_EXIT || 0));
    }
  `;
  mkdirSync(dirname(nextBin), { recursive: true });
  writeFileSync(nextBin, fakeNext);
  writeFileSync(join(root, 'package.json'), JSON.stringify({ name: 'launcher-fixture', private: true }));
  writeFileSync(join(root, 'package-lock.json'), JSON.stringify({ lockfileVersion: 3 }));
  writeFileSync(join(root, 'fake-npm.cjs'), `
    const fs = require('node:fs');
    const path = require('node:path');
    fs.appendFileSync('npm-calls.jsonl', JSON.stringify(process.argv.slice(2)) + '\\n');
    const code = Number(process.env.LAUNCHER_TEST_NPM_EXIT || 0);
    if (code) process.exit(code);
    const next = path.join('node_modules', 'next', 'dist', 'bin', 'next');
    fs.mkdirSync(path.dirname(next), {recursive: true});
    fs.writeFileSync(next, ${JSON.stringify(fakeNext)});
  `);
  const preload = join(root, 'mock-npm.mjs');
  writeFileSync(preload, `
    import childProcess from 'node:child_process';
    import { syncBuiltinESMExports } from 'node:module';
    import { appendFileSync } from 'node:fs';
    import { join } from 'node:path';
    const originalSpawn = childProcess.spawn;
    childProcess.spawn = (command, args, options) => {
      const child = command === 'npm'
        ? originalSpawn(process.execPath, [join(process.cwd(), 'fake-npm.cjs'), ...args], options)
        : originalSpawn(command, args, options);
      const originalKill = child.kill.bind(child);
      child.kill = signal => {
        appendFileSync('forwarded-signals.jsonl', JSON.stringify(signal) + '\\n');
        return originalKill(signal);
      };
      return child;
    };
    syncBuiltinESMExports();
    // Native SIGTERM forcibly terminates Windows processes. Deliver the same
    // launcher event over IPC to test its forwarding behavior on either OS.
    process.on('message', message => process.emit(message.signal));
    process.channel?.unref();
  `);
  const args = ['--import', pathToFileURL(preload).href, launcher];
  const run = (extra = [], env = {}) => spawnSync(process.execPath, [...args, ...extra], {
    cwd: root, env: { ...process.env, ...env }, encoding: 'utf8', timeout: 10000,
  });
  const record = () => {
    const result = run(['--record-installed']);
    assert.equal(result.status, 0, result.stderr);
  };
  const npmCalls = () => existsSync(join(root, 'npm-calls.jsonl'))
    ? readFileSync(join(root, 'npm-calls.jsonl'), 'utf8').trim().split('\n').map(line => JSON.parse(line))
    : [];
  return { root, nextBin, marker, args, run, record, npmCalls };
}

test('a matching dependency volume starts Next with Docker HMR arguments without npm', t => {
  const f = fixture(t);
  f.record();
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout.trim()), [
    'dev', '--webpack', '--hostname', '0.0.0.0', '--port', '3000',
  ]);
  assert.deepEqual(f.npmCalls(), []);
});

test('changing either manifest refreshes dependencies once and reuses them afterward', t => {
  const f = fixture(t);
  f.record();
  for (const [index, file] of ['package.json', 'package-lock.json'].entries()) {
    const oldMarker = readFileSync(f.marker, 'utf8');
    writeFileSync(join(f.root, file), JSON.stringify({ changed: index }));
    const result = f.run();
    assert.equal(result.status, 0, result.stderr);
    assert.notEqual(readFileSync(f.marker, 'utf8'), oldMarker);
    assert.deepEqual(f.npmCalls(), Array.from({ length: index + 1 }, () => ['ci', '--no-audit', '--no-fund']));
    assert.equal(f.run().status, 0);
    assert.equal(f.npmCalls().length, index + 1);
  }
});

test('a dependency volume with no marker or missing Next is repaired', t => {
  const f = fixture(t);
  assert.equal(f.run().status, 0);
  assert.equal(f.npmCalls().length, 1);
  rmSync(f.nextBin);
  assert.equal(f.run().status, 0);
  assert.equal(f.npmCalls().length, 2);
  assert.ok(existsSync(f.nextBin));
});

test('a failed npm refresh stops startup and preserves the previous installation marker', t => {
  const f = fixture(t);
  f.record();
  const oldMarker = readFileSync(f.marker, 'utf8');
  writeFileSync(join(f.root, 'package-lock.json'), '{"lockfileVersion":3,"changed":true}');
  const result = f.run([], { LAUNCHER_TEST_NPM_EXIT: '23' });
  assert.equal(result.status, 23, result.stderr);
  assert.equal(readFileSync(f.marker, 'utf8'), oldMarker);
  assert.doesNotMatch(result.stdout, /--webpack/);
});

test('a Next failure is returned to Docker', t => {
  const f = fixture(t);
  f.record();
  assert.equal(f.run([], { LAUNCHER_TEST_NEXT_EXIT: '17' }).status, 17);
});

test('shutdown forwards SIGTERM to Next and lets the launcher stop', { timeout: 15000 }, async t => {
  const f = fixture(t);
  f.record();
  const child = spawn(process.execPath, f.args, {
    cwd: f.root,
    env: { ...process.env, LAUNCHER_TEST_WAIT: '1' },
    stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
  });
  t.after(() => { if (child.exitCode === null) child.kill('SIGKILL'); });
  let stdout = '';
  let stderr = '';
  child.stderr.on('data', chunk => { stderr += chunk; });
  const stopped = new Promise((accept, reject) => {
    child.once('error', reject);
    child.once('close', code => accept(code));
  });
  await new Promise((accept, reject) => {
    const timer = setTimeout(() => reject(new Error(`Next fixture did not start: ${stderr}`)), 8000);
    child.stdout.on('data', chunk => {
      stdout += chunk;
      if (stdout.includes('NEXT_READY')) {
        clearTimeout(timer);
        accept();
      }
    });
  });
  child.send({ signal: 'SIGTERM' });
  assert.equal(await stopped, 0, stderr);
  assert.deepEqual(readFileSync(join(f.root, 'forwarded-signals.jsonl'), 'utf8').trim().split('\n').map(line => JSON.parse(line)), ['SIGTERM']);
});
