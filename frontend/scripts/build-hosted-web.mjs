// Keep application and asset credentials out of the Vite/npm process. Coolify
// mounts only these allowlisted values for this RUN; public CI can use ARGs.
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

export const webBuildSettings = [
  'VITE_API_URL', 'VITE_ALLOW_SIGNUP', 'VITE_SENTRY_DSN', 'VITE_SENTRY_ENVIRONMENT',
  'VITE_SENTRY_TRACES_SAMPLE_RATE', 'VITE_SENTRY_RELEASE',
  'SENTRY_AUTH_TOKEN', 'SENTRY_ORG', 'SENTRY_PROJECT',
]
const systemSettings = ['PATH', 'Path', 'HOME', 'TMPDIR', 'TMP', 'TEMP', 'SystemRoot',
  'ComSpec', 'PATHEXT', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'CI', 'NO_COLOR', 'FORCE_COLOR']

export async function webBuildEnvironment(env = process.env, readSecret = name => readFile(`/run/secrets/${name}`, 'utf8')) {
  const child = Object.fromEntries([...systemSettings, ...webBuildSettings].filter(key => env[key] !== undefined).map(key => [key, env[key]]))
  for (const name of webBuildSettings) {
    try {
      const value = await readSecret(name)
      if (value.length > 16384 || /[\r\n\0]/.test(value.trim())) throw new Error(`Invalid web build setting: ${name}`)
      child[name] = value.trim()
    } catch (error) { if (error.code !== 'ENOENT') throw error }
  }
  return child
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const env = await webBuildEnvironment()
    const result = spawnSync('npm', ['run', 'build'], { env, stdio: 'inherit', windowsHide: true })
    if (result.error || result.status !== 0) throw new Error('Hosted web build failed')
  } catch (error) { console.error(error.message); process.exitCode = 1 }
}
