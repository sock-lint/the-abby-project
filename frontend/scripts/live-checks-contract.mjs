import { constants } from 'node:fs';
import { lstat, open } from 'node:fs/promises';
import { isAbsolute } from 'node:path';

export const LIVE_BASE_URL = 'https://abby.bos.lol';
export const LIVE_FAMILY_SLUG = 'abby-live-checks';
export const LIVE_APPLICATION_UUID = 'lr5dn6lhga31vyk6u5qvhm4c';
export const CHECK_NAMES = ['deployment', 'health', 'publicShell', 'parent', 'child', 'isolation', 'cleanup'];
export const FRESHNESS_MS = 5 * 60_000;
const SHA = /^[a-f0-9]{40}$/;
const FAILURE_CODES = new Set([
  'CONFIGURATION', 'PRIVATE_FILE', 'SOURCE_REVISION', 'LOCK_BUSY', 'DEPLOYMENT_PROOF',
  'HEALTH', 'PUBLIC_SHELL', 'PARENT', 'CHILD', 'ISOLATION', 'CLEANUP',
  'IDENTITY', 'UNEXPECTED_MUTATION', 'EXTERNAL_AUTH', 'EXTERNAL_NAVIGATION',
  'BROWSER', 'TIMEOUT', 'INTERRUPTED', 'RUNNER',
]);

export class LiveCheckError extends Error {
  constructor(code) {
    super(FAILURE_CODES.has(code) ? code : 'RUNNER');
    this.code = this.message;
  }
}

export function requireCheck(condition, code = 'CONFIGURATION') {
  if (!condition) throw new LiveCheckError(code);
}

function exactKeys(value, keys, code = 'CONFIGURATION') {
  requireCheck(value && typeof value === 'object' && !Array.isArray(value), code);
  requireCheck(Object.keys(value).sort().join(',') === [...keys].sort().join(','), code);
}

export function validateCommit(value, code = 'CONFIGURATION') {
  requireCheck(typeof value === 'string' && SHA.test(value), code);
  return value;
}

export function validateCredentials(value) {
  exactKeys(value, ['schemaVersion', 'baseUrl', 'familySlug', 'familyId', 'parent', 'child']);
  requireCheck(value.schemaVersion === 1 && value.baseUrl === LIVE_BASE_URL
    && value.familySlug === LIVE_FAMILY_SLUG && Number.isSafeInteger(value.familyId)
    && value.familyId > 0);
  for (const role of ['parent', 'child']) {
    exactKeys(value[role], ['id', 'username', 'password']);
    requireCheck(Number.isSafeInteger(value[role].id) && value[role].id > 0
      && value[role].username === `abby_loop_${role}`
      && typeof value[role].password === 'string'
      && value[role].password.length >= 16 && value[role].password.length <= 256);
  }
  requireCheck(value.parent.id !== value.child.id);
  return value;
}

export function validateDeploymentProof(value, expectedCommit, now = Date.now()) {
  const code = 'DEPLOYMENT_PROOF';
  exactKeys(value, ['schemaVersion', 'source', 'applicationUuid', 'repository', 'branch',
    'deploymentUuid', 'status', 'commit', 'observedAt', 'expiresAt'], code);
  validateCommit(expectedCommit, code);
  requireCheck(value.schemaVersion === 1 && value.source === 'coolify'
    && value.applicationUuid === LIVE_APPLICATION_UUID
    && value.repository === 'sock-lint/the-abby-project' && value.branch === 'main'
    && value.status === 'finished' && value.commit === expectedCommit
    && typeof value.deploymentUuid === 'string' && /^[a-z0-9]{1,80}$/i.test(value.deploymentUuid), code);
  const observed = Date.parse(value.observedAt);
  const expires = Date.parse(value.expiresAt);
  requireCheck(typeof value.observedAt === 'string' && typeof value.expiresAt === 'string'
    && Number.isFinite(observed) && Number.isFinite(expires)
    && observed <= now && now - observed <= FRESHNESS_MS
    && expires > now && expires > observed && expires - observed <= FRESHNESS_MS, code);
  return value;
}

export function validateSourceManifest(value) {
  exactKeys(value, ['schemaVersion', 'sourceCommit'], 'SOURCE_REVISION');
  requireCheck(value.schemaVersion === 1, 'SOURCE_REVISION');
  return validateCommit(value.sourceCommit, 'SOURCE_REVISION');
}

export function validateIdentity(body, credentials, role, { login = false } = {}) {
  const actor = credentials[role];
  requireCheck(body && body.id === actor.id && body.username === actor.username
    && body.role === role && body.family?.id === credentials.familyId
    && body.family?.slug === LIVE_FAMILY_SLUG, 'IDENTITY');
  if (login) validateCommit(body.token, 'IDENTITY');
  return body;
}

export function validateHealth(body, expectedCommit) {
  requireCheck(body?.status === 'ok' && body.db === 'up'
    && body.commit === validateCommit(expectedCommit, 'HEALTH')
    && body.resourceUuid === LIVE_APPLICATION_UUID, 'HEALTH');
  return body.commit;
}

function privateStat(stat) {
  requireCheck(stat.isFile() && stat.nlink === 1 && (stat.mode & 0o777) === 0o600
    && (typeof process.getuid !== 'function' || stat.uid === process.getuid()), 'PRIVATE_FILE');
}

export function validatePrivatePath(path) {
  requireCheck(typeof path === 'string' && isAbsolute(path) && !path.includes('\0'), 'PRIVATE_FILE');
  return path;
}

// Open without following a final symlink, then verify the opened inode. The
// lstat check also rejects symlinks on platforms without O_NOFOLLOW support.
export async function readPrivateJson(path) {
  validatePrivatePath(path);
  let handle;
  try {
    const initial = await lstat(path);
    privateStat(initial);
    handle = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW || 0));
    const actual = await handle.stat();
    privateStat(actual);
    requireCheck(initial.dev === actual.dev && initial.ino === actual.ino && actual.size <= 65_536, 'PRIVATE_FILE');
    return JSON.parse(await handle.readFile('utf8'));
  } catch (error) {
    throw error instanceof LiveCheckError ? error : new LiveCheckError('PRIVATE_FILE');
  } finally {
    await handle?.close();
  }
}

export async function writePrivateJson(path, value) {
  validatePrivatePath(path);
  let handle;
  try {
    let initial;
    try { initial = await lstat(path); } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    if (initial) privateStat(initial);
    const flags = constants.O_WRONLY | (constants.O_NOFOLLOW || 0)
      | (initial ? 0 : constants.O_CREAT | constants.O_EXCL);
    handle = await open(path, flags, 0o600);
    const actual = await handle.stat();
    privateStat(actual);
    requireCheck(!initial || (initial.dev === actual.dev && initial.ino === actual.ino), 'PRIVATE_FILE');
    await handle.truncate(0);
    await handle.writeFile(`${JSON.stringify(value)}\n`, 'utf8');
    await handle.sync();
  } catch (error) {
    throw error instanceof LiveCheckError ? error : new LiveCheckError('PRIVATE_FILE');
  } finally {
    await handle?.close();
  }
}

export function newResult({ expectedCommit, sourceCommit, proof, credentials, now = Date.now() }) {
  return {
    schemaVersion: 1,
    status: 'failed',
    checkedAt: new Date(now).toISOString(),
    expiresAt: new Date(Math.min(now + FRESHNESS_MS,
      proof ? Date.parse(proof.expiresAt) : now + FRESHNESS_MS)).toISOString(),
    baseUrl: LIVE_BASE_URL,
    sourceCommit: SHA.test(sourceCommit || '') ? sourceCommit : null,
    expectedCommit: SHA.test(expectedCommit || '') ? expectedCommit : null,
    deployedCommit: proof?.commit || null,
    servedCommit: null,
    scope: credentials ? {
      familySlug: LIVE_FAMILY_SLUG, familyId: credentials.familyId,
      parentId: credentials.parent.id, childId: credentials.child.id,
    } : null,
    deployment: proof ? {
      source: 'coolify', applicationUuid: LIVE_APPLICATION_UUID,
      deploymentUuid: proof.deploymentUuid, repository: 'sock-lint/the-abby-project',
      branch: 'main', status: 'finished', observedAt: proof.observedAt,
    } : null,
    checks: Object.fromEntries(CHECK_NAMES.map((name) => [name, false])),
    failures: [],
  };
}

export function addFailure(result, code) {
  const fixed = FAILURE_CODES.has(code) ? code : 'RUNNER';
  if (!result.failures.includes(fixed)) result.failures.push(fixed);
  result.status = 'failed';
}

// An allowlist reconstruction is deliberately used instead of redacting raw
// Playwright output. Payloads, user identities and arbitrary error text never
// become part of the persisted report.
export function sanitizedResult(value) {
  const result = newResult({
    expectedCommit: value.expectedCommit, sourceCommit: value.sourceCommit,
    now: Number.isFinite(Date.parse(value.checkedAt)) ? Date.parse(value.checkedAt) : Date.now(),
  });
  result.expiresAt = Number.isFinite(Date.parse(value.expiresAt))
    ? new Date(Math.min(Date.parse(value.expiresAt), Date.parse(result.expiresAt))).toISOString()
    : result.expiresAt;
  if (value.deployedCommit && SHA.test(value.deployedCommit)) result.deployedCommit = value.deployedCommit;
  if (value.servedCommit && SHA.test(value.servedCommit)) result.servedCommit = value.servedCommit;
  const scope = value.scope;
  if (scope?.familySlug === LIVE_FAMILY_SLUG
    && [scope.familyId, scope.parentId, scope.childId].every((id) => Number.isSafeInteger(id) && id > 0)
    && scope.parentId !== scope.childId) {
    result.scope = { familySlug: LIVE_FAMILY_SLUG, familyId: scope.familyId,
      parentId: scope.parentId, childId: scope.childId };
  }
  const deployment = value.deployment;
  if (deployment?.source === 'coolify' && deployment.applicationUuid === LIVE_APPLICATION_UUID
    && /^[a-z0-9]{1,80}$/i.test(deployment.deploymentUuid || '')
    && deployment.repository === 'sock-lint/the-abby-project' && deployment.branch === 'main'
    && deployment.status === 'finished' && Number.isFinite(Date.parse(deployment.observedAt))) {
    result.deployment = {
      source: 'coolify', applicationUuid: LIVE_APPLICATION_UUID,
      deploymentUuid: deployment.deploymentUuid, repository: 'sock-lint/the-abby-project',
      branch: 'main', status: 'finished', observedAt: new Date(deployment.observedAt).toISOString(),
    };
  }
  for (const name of CHECK_NAMES) result.checks[name] = value.checks?.[name] === true;
  for (const code of Array.isArray(value.failures) ? value.failures : []) addFailure(result, code);
  if (/^[a-f0-9]{32}$/i.test(value.spaEtag || '')) result.spaEtag = value.spaEtag;
  result.status = result.failures.length === 0 && CHECK_NAMES.every((name) => result.checks[name])
    && result.sourceCommit && result.expectedCommit === result.deployedCommit
    && result.expectedCommit === result.servedCommit && result.deployment && result.scope ? 'passed' : 'failed';
  return result;
}
