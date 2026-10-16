import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { webBuildEnvironment, webBuildSettings } from './build-hosted-web.mjs'

const absent = async () => { throw Object.assign(new Error('Synthetic missing mount'), { code: 'ENOENT' }) }

test('Vite receives only explicit web settings and operating-system essentials', async () => {
  const input = { PATH: '/synthetic/bin', HOME: '/synthetic/home', VITE_ALLOW_SIGNUP: 'true',
    SENTRY_AUTH_TOKEN: 'synthetic-sourcemap-token', STAGING_SECRET_KEY: 'synthetic-signing-key',
    STAGING_DATABASE_PASSWORD: 'synthetic-db-key', ABBY_ASSETS_ACCESS_KEY_ID: 'synthetic-reader-key',
    ABBY_ASSETS_SECRET_ACCESS_KEY: 'synthetic-reader-secret', AWS_SECRET_ACCESS_KEY: 'synthetic-unrelated-key',
    COOLIFY_API_TOKEN: 'synthetic-management-token', COOLIFY_SSH_KEY: '/synthetic/private-key' }
  const child = await webBuildEnvironment(input, absent)
  assert.deepEqual(child, { PATH: '/synthetic/bin', HOME: '/synthetic/home', VITE_ALLOW_SIGNUP: 'true', SENTRY_AUTH_TOKEN: 'synthetic-sourcemap-token' })
  assert.equal(input.STAGING_SECRET_KEY, 'synthetic-signing-key')
})

test('explicit BuildKit mounts override public build argument defaults', async () => {
  const requested = []
  const child = await webBuildEnvironment({ VITE_ALLOW_SIGNUP: 'true' }, async name => {
    requested.push(name)
    if (name === 'VITE_ALLOW_SIGNUP') return 'false\n'
    return absent()
  })
  assert.equal(child.VITE_ALLOW_SIGNUP, 'false')
  assert.deepEqual(requested, webBuildSettings)
})

test('oversized or multiline web settings fail before spawning a build', async () => {
  for (const value of ['x'.repeat(16385), 'first\nsecond', 'zero\0byte']) {
    await assert.rejects(webBuildEnvironment({}, async () => value), /Invalid web build setting/)
  }
})

test('every Docker RUN explicitly scopes Coolify secret injection', async () => {
  const dockerfile = await readFile(new URL('../../Dockerfile', import.meta.url), 'utf8')
  for (const line of dockerfile.split('\n').filter(line => line.startsWith('RUN '))) assert.match(line, /--mount=type=secret/)
  for (const key of webBuildSettings) assert.match(dockerfile, new RegExp(`id=${key}(?:[ \\\\r\\n]|$)`))
})
