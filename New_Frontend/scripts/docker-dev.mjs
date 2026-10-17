import { createHash } from 'node:crypto';
import { access, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { spawn } from 'node:child_process';

// A persistent Linux node_modules volume survives image rebuilds. Compare its
// installation with the current bind-mounted manifests before starting Next.
const root = process.cwd();
const marker = join(root, 'node_modules', '.docker-dev-dependencies');
const nextBin = join(root, 'node_modules', 'next', 'dist', 'bin', 'next');
const hash = createHash('sha256');
hash.update(`${process.platform}:${process.arch}:${process.versions.node}\n`);
for (const filename of ['package.json', 'package-lock.json']) {
  hash.update(await readFile(join(root, filename)));
}
const fingerprint = hash.digest('hex');

let child;
let stopping = false;
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => {
    stopping = true;
    child?.kill(signal);
  });
}

function run(command, args) {
  return new Promise((resolve, reject) => {
    child = spawn(command, args, { cwd: root, stdio: 'inherit' });
    child.once('error', reject);
    child.once('exit', (code, signal) => {
      child = undefined;
      if (stopping) resolve(0);
      else if (signal) reject(new Error(`${command} exited with ${signal}`));
      else resolve(code ?? 1);
    });
  });
}

try {
  if (process.argv.includes('--record-installed')) {
    await access(nextBin);
    await writeFile(marker, fingerprint);
  } else {
    const installed = await readFile(marker, 'utf8').catch(() => '');
    const hasNext = await access(nextBin).then(() => true, () => false);
    if (installed !== fingerprint || !hasNext) {
      console.log('Refreshing container dependencies from package-lock.json...');
      const code = await run('npm', ['ci', '--no-audit', '--no-fund']);
      if (code !== 0) process.exit(code);
      if (!stopping) await writeFile(marker, fingerprint);
    }
    if (!stopping) {
      process.exitCode = await run(process.execPath, [
        nextBin, 'dev', '--webpack', '--hostname', '0.0.0.0', '--port', '3000',
      ]);
    }
  }
} catch (error) {
  console.error(`Frontend development startup failed: ${error.message}`);
  process.exitCode = 1;
}
