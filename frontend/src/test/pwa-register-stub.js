// Stub for virtual:pwa-register used by vitest.config.js alias.
// In tests, this module is always replaced by vi.mock('virtual:pwa-register').
// The alias only exists so Vite's import-analysis pass can resolve the
// virtual module path before the mock intercepts it at runtime.
export function registerSW() {
  return () => {};
}
