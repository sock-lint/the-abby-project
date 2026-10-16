import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
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

test('the browser DSN reaches Vite from the build environment or an overriding mount', async () => {
  const input = { VITE_SENTRY_DSN: 'https://synthetic-public@logs.example.invalid/12' }
  const mountedDsn = 'https://synthetic-mounted@logs.example.invalid/34'
  assert.equal((await webBuildEnvironment(input, absent)).VITE_SENTRY_DSN, input.VITE_SENTRY_DSN)
  const mounted = await webBuildEnvironment(input, name => name === 'VITE_SENTRY_DSN' ? `${mountedDsn}\n` : absent())
  assert.equal(mounted.VITE_SENTRY_DSN, mountedDsn)
  assert.equal(input.VITE_SENTRY_DSN, 'https://synthetic-public@logs.example.invalid/12')
  assert.equal((await webBuildEnvironment({}, absent)).VITE_SENTRY_DSN, undefined)
})

test('Compose forwards public browser Sentry settings to the build without the upload token', async () => {
  const configured = {
    VITE_SENTRY_DSN: 'https://synthetic-public@logs.example.invalid/12',
    VITE_SENTRY_ENVIRONMENT: 'synthetic',
    VITE_SENTRY_TRACES_SAMPLE_RATE: '0.125',
    VITE_SENTRY_RELEASE: 'synthetic-release',
  }
  const defaults = {
    VITE_SENTRY_DSN: '',
    VITE_SENTRY_ENVIRONMENT: 'production',
    VITE_SENTRY_TRACES_SAMPLE_RATE: '0.2',
    VITE_SENTRY_RELEASE: '',
  }
  const directory = await mkdtemp(join(tmpdir(), 'abby-sentry-build-'))
  try {
    for (const settings of [configured, {}]) {
      const envFile = join(directory, '.env')
      await writeFile(envFile, Object.entries({
        SECRET_KEY: 'synthetic-signing-key',
        SENTRY_AUTH_TOKEN: 'synthetic-upload-token',
        ...settings,
      }).map(([key, value]) => `${key}=${value}`).join('\n'))
      // Render only: both interpolation and runtime env_file paths use the
      // disposable project's synthetic .env. Docker configuration and the
      // working directory are isolated too; no daemon or network is used.
      const env = Object.fromEntries(['PATH', 'Path', 'SystemRoot', 'ComSpec', 'PATHEXT']
        .filter(key => process.env[key] !== undefined).map(key => [key, process.env[key]]))
      const output = execFileSync('docker', ['compose', '--project-directory', directory,
        '--env-file', envFile, '-f', fileURLToPath(new URL('../../docker-compose.yml', import.meta.url)),
        'config', '--format', 'json'], {
        cwd: directory,
        env: { ...env, HOME: directory, USERPROFILE: directory, DOCKER_CONFIG: directory },
        encoding: 'utf8',
      })
      const build = JSON.parse(output).services.django.build
      assert.deepEqual(build.args, settings === configured ? configured : defaults)
      assert.equal(Object.hasOwn(build.args, 'SENTRY_AUTH_TOKEN'), false)
      assert.equal(JSON.stringify(build).includes('synthetic-upload-token'), false)
    }
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
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
