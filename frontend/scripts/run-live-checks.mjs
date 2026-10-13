import { execFile, spawn } from 'node:child_process';
import { constants } from 'node:fs';
import { lstat, mkdir, mkdtemp, open, readFile, realpath, rm } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import {
  addFailure, LiveCheckError, newResult, readPrivateJson, requireCheck, sanitizedResult,
  validateCommit, validateCredentials, validateDeploymentProof, validatePrivatePath,
  validateSourceManifest, writePrivateJson,
} from './live-checks-contract.mjs';
import { LiveProcessGroup } from './live-process-group.mjs';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const runFile = promisify(execFile);
const options = {};
let result;
let child;
let lock;
let lockPath;
let directory;
let interrupted = false;
let ownsLock = false;
let timedOut = false;
let supervisor;

function interrupt() {
  interrupted = true;
  void supervisor?.stop();
}

process.once('SIGINT', interrupt);
process.once('SIGTERM', interrupt);

async function sourceRevision() {
  const path = join(frontendRoot, '.abby-live-source.json');
  try {
    const stat = await lstat(path);
    requireCheck(stat.isFile() && stat.nlink === 1 && stat.uid === 0
      && (stat.mode & 0o022) === 0, 'SOURCE_REVISION');
    const revision = validateSourceManifest(JSON.parse(await readFile(path, 'utf8')));
    requireCheck(frontendRoot === `/opt/abby-live-checks/${revision}/frontend`, 'SOURCE_REVISION');
    return revision;
  } catch (error) {
    if (error.code !== 'ENOENT') throw new LiveCheckError('SOURCE_REVISION');
    const git = await runFile('git', ['-C', resolve(frontendRoot, '..'), 'rev-parse', 'HEAD']);
    return validateCommit(git.stdout.trim(), 'SOURCE_REVISION');
  }
}

async function acquireLock() {
  const state = join(homedir(), '.local', 'state', 'abby-live-checks');
  await mkdir(state, { recursive: true, mode: 0o700 });
  const stat = await lstat(state);
  requireCheck(stat.isDirectory() && (stat.mode & 0o777) === 0o700
    && (typeof process.getuid !== 'function' || stat.uid === process.getuid()), 'PRIVATE_FILE');
  lockPath = join(state, 'browser.lock');
  try {
    lock = await open(lockPath, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL
      | (constants.O_NOFOLLOW || 0), 0o600);
    ownsLock = true;
    await lock.writeFile(JSON.stringify({ pid: process.pid, createdAt: new Date().toISOString() }));
  } catch (error) {
    throw new LiveCheckError(error.code === 'EEXIST' ? 'LOCK_BUSY' : 'PRIVATE_FILE');
  }
}

try {
  requireCheck(process.platform === 'linux');
  const allowed = ['--credentials-file', '--deployment-proof-file', '--result-file', '--expected-commit'];
  const args = process.argv.slice(2);
  requireCheck(args.length === allowed.length * 2);
  for (let i = 0; i < args.length; i += 2) {
    requireCheck(allowed.includes(args[i]) && options[args[i]] === undefined && Boolean(args[i + 1]));
    options[args[i]] = args[i + 1];
  }
  validatePrivatePath(options['--result-file']);
  const inputPaths = await Promise.all(['--credentials-file', '--deployment-proof-file'].map(async (key) =>
    realpath(validatePrivatePath(options[key]))));
  const outputPath = await realpath(options['--result-file']).catch(async (error) => {
    if (error.code !== 'ENOENT') throw error;
    return join(await realpath(dirname(options['--result-file'])), basename(options['--result-file']));
  });
  requireCheck(new Set([...inputPaths, outputPath]).size === 3, 'PRIVATE_FILE');
  result = newResult({ expectedCommit: options['--expected-commit'] });
  await writePrivateJson(options['--result-file'], result);
  const expectedCommit = validateCommit(options['--expected-commit']);
  const sourceCommit = await sourceRevision();
  const credentials = validateCredentials(await readPrivateJson(options['--credentials-file']));
  const proof = validateDeploymentProof(await readPrivateJson(options['--deployment-proof-file']), expectedCommit);
  result = newResult({ expectedCommit, sourceCommit, proof, credentials });
  await writePrivateJson(options['--result-file'], result);
  await acquireLock();
  directory = await mkdtemp(join(tmpdir(), 'abby-live-'));
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    /^(PATH|HOME|USERPROFILE|SYSTEMROOT|WINDIR|TEMP|TMP|LANG|LC_ALL|XDG_CACHE_HOME|PLAYWRIGHT_BROWSERS_PATH)$/i.test(key)));
  Object.assign(env, {
    ABBY_LIVE_GUARDED_RUN: '1',
    ABBY_LIVE_CREDENTIALS_FILE: options['--credentials-file'],
    ABBY_LIVE_DEPLOYMENT_PROOF_FILE: options['--deployment-proof-file'],
    ABBY_LIVE_RESULT_FILE: options['--result-file'],
    ABBY_LIVE_EXPECTED_COMMIT: expectedCommit,
    ABBY_LIVE_SOURCE_COMMIT: sourceCommit,
    ABBY_LIVE_OUTPUT_DIRECTORY: directory,
  });
  requireCheck(!interrupted, 'INTERRUPTED');
  child = spawn(process.execPath, [join(frontendRoot, 'node_modules', '@playwright', 'test', 'cli.js'),
    'test', '--config', join(frontendRoot, 'playwright.live.config.js')],
  { cwd: frontendRoot, env, stdio: 'ignore', detached: true });
  supervisor = new LiveProcessGroup(child);
  const exitPromise = new Promise((resolveExit) => {
    // Reserve shutdown time inside the overall 180-second bound.
    const timer = setTimeout(() => { timedOut = true; void supervisor.stop(); }, 175_000);
    child.once('error', () => { clearTimeout(timer); resolveExit(1); });
    child.once('close', (code) => { clearTimeout(timer); resolveExit(code ?? 1); });
  });
  await supervisor.start();
  const exit = await exitPromise;
  result = sanitizedResult(await readPrivateJson(options['--result-file']));
  if (timedOut || interrupted) {
    result.checks.cleanup = false;
    addFailure(result, timedOut ? 'TIMEOUT' : 'INTERRUPTED');
  } else if (exit !== 0) addFailure(result, 'RUNNER');
  await writePrivateJson(options['--result-file'], sanitizedResult(result));
  process.exitCode = result.status === 'passed' && exit === 0 ? 0 : 1;
} catch (error) {
  if (result) {
    addFailure(result, error instanceof LiveCheckError ? error.code : 'RUNNER');
    try { await writePrivateJson(options['--result-file'], sanitizedResult(result)); } catch { /* No raw diagnostics. */ }
  }
  process.exitCode = 1;
} finally {
  process.removeListener('SIGINT', interrupt);
  process.removeListener('SIGTERM', interrupt);
  let cleaned = true;
  try {
    if (supervisor && !await supervisor.stop()) { cleaned = false; ownsLock = false; }
    await lock?.close();
    if (ownsLock) await rm(lockPath, { force: true });
    if (directory) await rm(directory, { recursive: true, force: true });
  } catch { cleaned = false; }
  if (!cleaned && result) {
    result.checks.cleanup = false;
    addFailure(result, 'CLEANUP');
    try { await writePrivateJson(options['--result-file'], sanitizedResult(result)); } catch { /* Fixed result only. */ }
    process.exitCode = 1;
  }
}
