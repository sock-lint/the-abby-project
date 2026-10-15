import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { SHARED_ASSET_SECRET_NAMES, sharedAssetsEnvironment, sharedAssetsRequired } from './shared-assets-config.mjs';

test('optional builds and an explicit requirement are distinct', () => {
  assert.equal(sharedAssetsRequired(undefined), false);
  assert.equal(sharedAssetsRequired('false'), false);
  assert.equal(sharedAssetsRequired('true'), true);
});

test('blank or malformed required build secrets fail instead of disabling the gate', () => {
  for (const value of ['', ' ', '\n', 'TRUE', '1', 'false ', null]) {
    assert.throws(() => sharedAssetsRequired(value), /must be true or false/);
  }
});

test('dedicated shared credentials override only the scoped process copy and discard stale profiles/tokens', () => {
  const environment = {
    AWS_ACCESS_KEY_ID: 'synthetic-old-media-key', AWS_SECRET_ACCESS_KEY: 'synthetic-old-media-secret',
    AWS_SESSION_TOKEN: 'synthetic-stale-token', AWS_PROFILE: 'old-media-profile', AWS_DEFAULT_PROFILE: 'old-default',
    ABBY_ASSETS_ACCESS_KEY_ID: 'synthetic-shared-reader', ABBY_ASSETS_SECRET_ACCESS_KEY: 'synthetic-shared-secret',
    UNRELATED_SETTING: 'preserved',
  };
  const result = sharedAssetsEnvironment(environment);
  assert.equal(result.AWS_ACCESS_KEY_ID, 'synthetic-shared-reader');
  assert.equal(result.AWS_SECRET_ACCESS_KEY, 'synthetic-shared-secret');
  for (const name of ['AWS_SESSION_TOKEN', 'AWS_PROFILE', 'AWS_DEFAULT_PROFILE']) assert.equal(result[name], undefined);
  assert.equal(result.UNRELATED_SETTING, 'preserved');
  assert.equal(environment.AWS_ACCESS_KEY_ID, 'synthetic-old-media-key');
  assert.equal(environment.AWS_PROFILE, 'old-media-profile');
  assert.equal(environment.AWS_SESSION_TOKEN, 'synthetic-stale-token');
});

test('local named profiles remain supported without dedicated credentials and explicit shared tokens are scoped', () => {
  const local = { AWS_PROFILE: 'abby-assets-abby-reader', AWS_SHARED_CREDENTIALS_FILE: '/synthetic/credentials' };
  assert.deepEqual(sharedAssetsEnvironment(local), local);
  const temporary = sharedAssetsEnvironment({ ...local, ABBY_ASSETS_ACCESS_KEY_ID: 'synthetic-key',
    ABBY_ASSETS_SECRET_ACCESS_KEY: 'synthetic-secret', ABBY_ASSETS_SESSION_TOKEN: 'synthetic-token' });
  assert.equal(temporary.AWS_SESSION_TOKEN, 'synthetic-token');
  assert.equal(temporary.AWS_PROFILE, undefined);
});

test('partial or blank dedicated credentials fail without disclosing any credential value', () => {
  for (const environment of [
    { ABBY_ASSETS_ACCESS_KEY_ID: 'sensitive-synthetic-value' },
    { ABBY_ASSETS_SECRET_ACCESS_KEY: 'sensitive-synthetic-value' },
    { ABBY_ASSETS_SESSION_TOKEN: 'sensitive-synthetic-value' },
    { ABBY_ASSETS_ACCESS_KEY_ID: '', ABBY_ASSETS_SECRET_ACCESS_KEY: 'sensitive-synthetic-value' },
    { ABBY_ASSETS_ACCESS_KEY_ID: 'sensitive-synthetic-value', ABBY_ASSETS_SECRET_ACCESS_KEY: '  ' },
    { ABBY_ASSETS_ACCESS_KEY_ID: 'sensitive-synthetic-value', ABBY_ASSETS_SECRET_ACCESS_KEY: 'synthetic-secret', ABBY_ASSETS_SESSION_TOKEN: '' },
  ]) {
    assert.throws(() => sharedAssetsEnvironment(environment), (error) => {
      assert.match(error.message, /ABBY_ASSETS_/);
      assert.ok(!error.message.includes('sensitive-synthetic-value'));
      return true;
    });
  }
});

test('shared mounts are distinct from legacy media credentials in the Docker build', async () => {
  assert.ok(!SHARED_ASSET_SECRET_NAMES.some((name) => name.startsWith('AWS_')));
  const dockerfile = await readFile(new URL('../../Dockerfile', import.meta.url), 'utf8');
  const shared = dockerfile.split('# Shared releases are pinned')[1].split('# Keep this RUN separate')[0];
  for (const name of ['ABBY_ASSETS_ACCESS_KEY_ID', 'ABBY_ASSETS_SECRET_ACCESS_KEY', 'ABBY_ASSETS_SESSION_TOKEN']) assert.ok(shared.includes(`id=${name}`));
  assert.ok(!shared.includes('id=AWS_ACCESS_KEY_ID'));
  assert.ok(!shared.includes('id=AWS_SECRET_ACCESS_KEY'));
  const legacy = dockerfile.split('# Shared releases are pinned')[0];
  assert.ok(legacy.includes('id=AWS_ACCESS_KEY_ID'));
  assert.ok(legacy.includes('id=AWS_SECRET_ACCESS_KEY'));
});
