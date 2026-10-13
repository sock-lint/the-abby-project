import assert from 'node:assert/strict';
import { execFile, spawn } from 'node:child_process';
import { once } from 'node:events';
import { chmod, link, lstat, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';
import {
  CHECK_NAMES, LIVE_APPLICATION_UUID, LIVE_BASE_URL, newResult, readPrivateJson,
  sanitizedResult, validateCredentials, validateDeploymentProof, validateHealth,
  validateIdentity, validateSourceManifest, writePrivateJson,
} from './live-checks-contract.mjs';
import { LiveProcessGroup } from './live-process-group.mjs';
import { installRedirectFence, installRequestGate, RequestGate } from '../e2e/live-smoke/request-gate.js';

const commit = 'a'.repeat(40);
const sourceCommit = 'b'.repeat(40);
const credentials = () => ({ schemaVersion: 1, baseUrl: LIVE_BASE_URL,
  familySlug: 'abby-live-checks', familyId: 11,
  parent: { id: 21, username: 'abby_loop_parent', password: 'synthetic-parent-password' },
  child: { id: 22, username: 'abby_loop_child', password: 'synthetic-child-password' } });
const proof = (now = Date.now()) => ({ schemaVersion: 1, source: 'coolify',
  applicationUuid: LIVE_APPLICATION_UUID, repository: 'sock-lint/the-abby-project', branch: 'main',
  deploymentUuid: 'syntheticdeployment', status: 'finished', commit,
  observedAt: new Date(now - 1_000).toISOString(), expiresAt: new Date(now + 240_000).toISOString() });
const identity = (role = 'parent') => ({ ...credentials()[role], role,
  family: { id: 11, slug: 'abby-live-checks' }, token: 'c'.repeat(40) });

test('credentials pin origin, reserved usernames, family and distinct provisioned IDs', () => {
  assert.equal(validateCredentials(credentials()).parent.username, 'abby_loop_parent');
  for (const baseUrl of ['http://abby.bos.lol', `${LIVE_BASE_URL}/`, `${LIVE_BASE_URL}?token=secret`,
    'https://secret@abby.bos.lol', 'https://abby.bos.lol:8443', 'https://other.example']) {
    assert.throws(() => validateCredentials({ ...credentials(), baseUrl }), { message: 'CONFIGURATION' });
  }
  for (const transform of [
    (c) => { delete c.familyId; }, (c) => { c.familyId = 0; },
    (c) => { c.familySlug = 'default-family'; }, (c) => { c.parent.username = 'real-parent'; },
    (c) => { c.child.id = c.parent.id; }, (c) => { c.child.password = 'short'; },
    (c) => { c.token = 'private'; },
  ]) {
    const changed = credentials(); transform(changed);
    assert.throws(() => validateCredentials(changed), { message: 'CONFIGURATION' });
  }
});

test('deployment proof must be exact target, finished, matching and fresh within five minutes', () => {
  const now = Date.now();
  assert.equal(validateDeploymentProof(proof(now), commit, now).commit, commit);
  for (const delta of [
    { commit: sourceCommit }, { branch: 'feature' }, { repository: 'other/repo' },
    { applicationUuid: 'otherapp' }, { status: 'running' }, { source: 'browser' },
    { observedAt: new Date(now + 1).toISOString() },
    { observedAt: new Date(now - 301_000).toISOString() },
    { expiresAt: new Date(now).toISOString() },
    { expiresAt: new Date(now + 301_000).toISOString() },
    { extra: 'response body' },
  ]) assert.throws(() => validateDeploymentProof({ ...proof(now), ...delta }, commit, now), { message: 'DEPLOYMENT_PROOF' });
});

test('source manifest pins harness independently from the deployed release', () => {
  assert.equal(validateSourceManifest({ schemaVersion: 1, sourceCommit }), sourceCommit);
  assert.throws(() => validateSourceManifest({ schemaVersion: 1, sourceCommitSHA: sourceCommit }), { message: 'SOURCE_REVISION' });
});

test('served health and authenticated identities fail closed on missing or mismatching targets', () => {
  const health = { status: 'ok', db: 'up', commit, resourceUuid: LIVE_APPLICATION_UUID };
  assert.equal(validateHealth(health, commit), commit);
  for (const delta of [{ db: 'down' }, { status: 'degraded' }, { commit: undefined },
    { commit: sourceCommit }, { resourceUuid: undefined }, { resourceUuid: 'otherapp' }]) {
    assert.throws(() => validateHealth({ ...health, ...delta }, commit), { message: 'HEALTH' });
  }
  assert.equal(validateIdentity(identity(), credentials(), 'parent', { login: true }).id, 21);
  for (const delta of [{ id: 999 }, { username: 'another-parent' }, { role: 'child' },
    { family: { id: 12, slug: 'abby-live-checks' } }, { token: 'bad' }]) {
    assert.throws(() => validateIdentity({ ...identity(), ...delta }, credentials(), 'parent', { login: true }), { message: 'IDENTITY' });
  }
});

test('request gate holds authenticated reads until exact identity verification and blocks unsafe requests', async () => {
  const gate = new RequestGate(credentials(), 'parent');
  const read = { url: `${LIVE_BASE_URL}/api/dashboard/`, method: 'GET', authorization: `Token ${identity().token}` };
  assert.equal(gate.inspect(read), 'hold');
  assert.equal(gate.inspect({ url: `${LIVE_BASE_URL}/api/auth/`, method: 'POST', body: {
    action: 'login', username: credentials().parent.username, password: credentials().parent.password,
  } }), 'allow');
  gate.accept(identity());
  assert.equal(await gate.identityReady, true);
  assert.equal(gate.inspect(read), 'allow');
  assert.equal(gate.inspect({ ...read, authorization: 'Token unexpected' }), 'abort');
  assert.equal(gate.inspect({ ...read, url: 'https://other.example/api/dashboard/' }), 'abort');
  assert.equal(gate.inspect({ url: `${LIVE_BASE_URL}/api/auth/me/`, method: 'PATCH', authorization: read.authorization }), 'abort');
  assert.equal(gate.inspect({ url: 'https://other.example/', method: 'GET', navigation: true }), 'abort');
  assert.equal(gate.inspect({ url: 'https://s3.neato.digital/synthetic.png', method: 'GET' }), 'allow');
  assert.deepEqual([...gate.failures].sort(), ['EXTERNAL_AUTH', 'EXTERNAL_NAVIGATION', 'IDENTITY', 'UNEXPECTED_MUTATION']);
});

test('failed identity never releases private API reads', async () => {
  const gate = new RequestGate(credentials(), 'child');
  const cleanupTokens = [];
  assert.throws(() => cleanupTokens.push(gate.accept(identity('parent'))), { message: 'IDENTITY' });
  assert.deepEqual(cleanupTokens, []);
  gate.cancel();
  assert.equal(await gate.identityReady, false);
  assert.equal(gate.verified, false);
});

test('observed Cloudflare background detection is discarded before forwarding in anonymous and verified contexts', async () => {
  for (const role of ['parent', 'child']) {
    const gate = new RequestGate(credentials(), role);
    if (role === 'child') gate.accept(identity(role));
    let handler;
    const context = {
      addInitScript: async () => {}, on: () => {},
      route: async (_pattern, callback) => { handler = callback; },
    };
    await installRequestGate(context, gate);
    const calls = [];
    await handler({
      request: () => ({
        url: () => `${LIVE_BASE_URL}/cdn-cgi/challenge-platform/h/g/jsd/oneshot/synthetic-challenge`,
        method: () => 'POST', headers: () => ({}), isNavigationRequest: () => false,
        postDataJSON: () => ({ synthetic: true }),
      }),
      abort: async (reason) => { calls.push(['abort', reason]); },
      continue: async () => { calls.push(['continue']); },
    });
    assert.deepEqual(calls, [['abort', 'blockedbyclient']]);
    gate.assertSafe();
    assert.deepEqual([...gate.failures], []);
  }
});

test('background detection exception is restricted to its observed method, origin, path boundary and uncredentialed non-navigation scope', () => {
  const path = '/cdn-cgi/challenge-platform/h/g/jsd/oneshot';
  const request = { url: `${LIVE_BASE_URL}${path}`, method: 'POST', navigation: false };
  const quiet = new RequestGate(credentials(), 'parent');
  assert.equal(quiet.inspect(request), 'abort');
  quiet.assertSafe();
  for (const change of [
    { url: `${LIVE_BASE_URL}${path}-unrelated` },
    { url: `${LIVE_BASE_URL}/cdn-cgi/challenge-platform/h/g/jsd/r/synthetic` },
    { url: `${LIVE_BASE_URL}/cdn-cgi/rum` },
    { url: `${LIVE_BASE_URL}/api/projects/` },
    { url: `${LIVE_BASE_URL}/api/auth/`, body: { action: 'logout' } },
    { method: 'DELETE' }, { authorization: `Token ${identity().token}` }, { navigation: true },
  ]) {
    const gate = new RequestGate(credentials(), 'parent');
    assert.equal(gate.inspect({ ...request, ...change }), 'abort');
    assert.throws(() => gate.assertSafe(), { message: 'UNEXPECTED_MUTATION' });
  }
  for (const url of ['https://other.example' + path, 'https://private@abby.bos.lol' + path]) {
    const gate = new RequestGate(credentials(), 'parent');
    assert.equal(gate.inspect({ ...request, url, authorization: 'Token synthetic' }), 'abort');
    assert.throws(() => gate.assertSafe(), { message: 'EXTERNAL_AUTH' });
  }
});

test('partial private API failures become fixed codes without retaining error payloads', () => {
  const gate = new RequestGate(credentials(), 'parent');
  gate.observeResponse(`${LIVE_BASE_URL}/api/homework/dashboard/?private=query`, 500);
  assert.throws(() => gate.assertSafe(), { message: 'BROWSER' });
  const healthy = new RequestGate(credentials(), 'child');
  healthy.observeResponse(`${LIVE_BASE_URL}/api/children/`, 403);
  healthy.observeResponse('https://other.example/error', 503);
  healthy.assertSafe();
  assert.deepEqual([...gate.failures], ['BROWSER']);
});

test('wrapper rejects aliased output paths without changing credentials or exposing diagnostics', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'abby-runner-'));
  const credentialPath = join(directory, 'credentials.json');
  const proofPath = join(directory, 'proof.json');
  const resultPath = join(directory, 'result.json');
  const runner = new URL('./run-live-checks.mjs', import.meta.url).pathname;
  try {
    await writePrivateJson(credentialPath, credentials());
    await writePrivateJson(proofPath, proof(Date.now() - 600_000));
    const original = await readFile(credentialPath, 'utf8');
    for (const output of [credentialPath, resultPath]) {
      const failure = await promisify(execFile)(process.execPath, [runner,
        '--credentials-file', credentialPath, '--deployment-proof-file', proofPath,
        '--result-file', output, '--expected-commit', commit]).catch((error) => error);
      assert.equal(failure.code, 1);
      assert.equal(failure.stdout, '');
      assert.equal(failure.stderr, '');
      assert.equal(await readFile(credentialPath, 'utf8'), original);
    }
    const report = await readPrivateJson(resultPath);
    assert.equal(report.status, 'failed');
    assert.deepEqual(report.failures, ['DEPLOYMENT_PROOF']);
    assert.equal(JSON.stringify(report).includes(credentials().parent.password), false);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test('native fetch fence refuses credential redirects while retaining real request contents', async () => {
  const previous = globalThis.window;
  const calls = [];
  globalThis.window = { fetch: async (input, options) => { calls.push(new Request(input, options)); return 'native-response'; } };
  try {
    installRedirectFence();
    assert.equal(await window.fetch(`${LIVE_BASE_URL}/api/auth/`, { method: 'POST',
      body: 'synthetic-password-body', headers: { 'Content-Type': 'application/json' } }), 'native-response');
    assert.equal(calls[0].redirect, 'error');
    assert.equal(await calls[0].text(), 'synthetic-password-body');
    await window.fetch(`${LIVE_BASE_URL}/api/dashboard/`, { headers: { Authorization: 'Token synthetic' } });
    assert.equal(calls[1].redirect, 'error');
    await window.fetch(`${LIVE_BASE_URL}/public/fonts/Nunito-Variable.ttf`);
    assert.equal(calls[2].redirect, 'follow');
  } finally {
    if (previous === undefined) delete globalThis.window;
    else globalThis.window = previous;
  }
});

test('report reconstruction excludes raw values and requires all evidence for a passing result', () => {
  const value = newResult({ expectedCommit: commit, sourceCommit, credentials: credentials(), proof: proof() });
  Object.assign(value, { status: 'passed', servedCommit: commit,
    password: 'do-not-persist', token: 'do-not-persist', stack: 'do-not-persist',
    response: { private: 'do-not-persist' }, spaEtag: 'd'.repeat(32),
    checks: Object.fromEntries(CHECK_NAMES.map((name) => [name, true])) });
  value.deployment.secret = 'do-not-persist';
  value.scope.secret = 'do-not-persist';
  assert.equal(sanitizedResult(value).status, 'passed');
  assert.equal(sanitizedResult(value).sourceCommit, sourceCommit);
  assert.equal(JSON.stringify(sanitizedResult(value)).includes('do-not-persist'), false);
  assert.equal(sanitizedResult({ ...value, checks: { ...value.checks, cleanup: false } }).status, 'failed');
  assert.equal(sanitizedResult({ ...value, servedCommit: sourceCommit }).status, 'failed');
  assert.deepEqual(sanitizedResult({ ...value, failures: ['private-token-text'] }).failures, ['RUNNER']);
});

test('private JSON files enforce ownership, mode, regular inode and no links', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'abby-contract-'));
  const path = join(directory, 'credentials.json');
  try {
    await writePrivateJson(path, credentials());
    assert.equal((await lstat(path)).mode & 0o777, 0o600);
    assert.equal((await readPrivateJson(path)).familyId, 11);
    await chmod(path, 0o644);
    await assert.rejects(readPrivateJson(path), { message: 'PRIVATE_FILE' });
    await chmod(path, 0o600);
    const symlinkPath = join(directory, 'symlink.json');
    await symlink(path, symlinkPath);
    await assert.rejects(readPrivateJson(symlinkPath), { message: 'PRIVATE_FILE' });
    await assert.rejects(writePrivateJson(symlinkPath, { rewritten: true }), { message: 'PRIVATE_FILE' });
    const hardlinkPath = join(directory, 'hardlink.json');
    await link(path, hardlinkPath);
    await assert.rejects(readPrivateJson(path), { message: 'PRIVATE_FILE' });
    await rm(hardlinkPath);
    await writeFile(path, 'not JSON', { mode: 0o600 });
    await assert.rejects(readPrivateJson(path), { message: 'PRIVATE_FILE' });
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test('shutdown drains a detached browser group that ignores SIGTERM', { skip: process.platform !== 'linux', timeout: 10_000 }, async () => {
  const code = `
    const { spawn } = require('node:child_process');
    const nested = spawn(process.execPath, ['-e', "process.on('SIGTERM', () => {}); setInterval(() => {}, 1000)"], { detached: true, stdio: 'ignore' });
    process.stdout.write(String(nested.pid) + '\\n');
    process.on('SIGTERM', () => {});
    setInterval(() => {}, 1000);
  `;
  const child = spawn(process.execPath, ['-e', code], { detached: true, stdio: ['ignore', 'pipe', 'ignore'] });
  const output = once(child.stdout, 'data');
  const group = new LiveProcessGroup(child);
  try {
    await group.start();
    const [data] = await output;
    const nestedPid = Number(data.toString().trim());
    await group.track();
    assert.equal(await group.stop(), true);
    const stat = await readFile(`/proc/${nestedPid}/stat`, 'utf8').catch(() => null);
    assert.equal(stat === null || stat.slice(stat.lastIndexOf(')') + 1).trim().startsWith('Z '), true);
  } finally {
    await group.stop();
  }
});
