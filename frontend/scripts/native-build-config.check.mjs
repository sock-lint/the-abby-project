import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { nativeBuildConfig } from './native-build-config.mjs';

test('native bundle requires an explicit isolated HTTPS staging origin', () => {
  const config = nativeBuildConfig({
    ABBY_NATIVE_ENVIRONMENT: 'staging',
    ABBY_NATIVE_API_ORIGIN: 'https://staging.abby.example/',
    VITE_API_URL: 'https://abby.bos.lol',
  });
  assert.equal(config.base, '/');
  assert.equal(config.outDir, 'dist-native');
  assert.equal(config.define['import.meta.env.VITE_API_URL'], '"https://staging.abby.example"');
  assert.equal(config.define['import.meta.env.VITE_NATIVE_BUILD'], '"true"');
});

test('missing configuration and production cannot become native defaults', () => {
  assert.throws(() => nativeBuildConfig({}), /staging/);
  for (const origin of [undefined, 'http://staging.example', 'https://abby.bos.lol',
    'https://user:password@staging.example', 'https://staging.example/api',
    'https://staging.example/?token=secret', 'https://staging.example/#credential']) {
    assert.throws(() => nativeBuildConfig({
      ABBY_NATIVE_ENVIRONMENT: 'staging', ABBY_NATIVE_API_ORIGIN: origin,
    }));
  }
});

test('Capacitor ships a local prototype bundle without a hosted server URL', async () => {
  const config = JSON.parse(await readFile(new URL('../capacitor.config.json', import.meta.url), 'utf8'));
  assert.equal(config.webDir, 'dist-native');
  assert.equal(config.appId, 'digital.neato.abby.prototype');
  assert.equal(config.server?.url, undefined);
});
