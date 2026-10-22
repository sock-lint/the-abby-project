// Exercise the ESM build selected by Vite, with the same Three instance as
// the scenes. Node's CJS entry has its own independent Three console hook.
import { createRoot, _roots } from '@react-three/fiber/dist/react-three-fiber.esm.js';
import { getConsoleFunction, setConsoleFunction } from 'three';
import { installThreeConsoleFilter } from './console';

const CLOCK_DEPRECATION = 'THREE.Clock: This module has been deprecated. Please use THREE.Timer instead.';
let previous;
beforeEach(() => {
  previous = getConsoleFunction();
  setConsoleFunction(null);
});
afterEach(() => {
  setConsoleFunction(previous);
  vi.restoreAllMocks();
});

it.each([
  '../avatar/AvatarScene.jsx',
  '../companion/CompanionScene.jsx',
  '../pedestal/PedestalScene.jsx',
])('initializes real R3F canvases without the upstream Clock warning via %s', async (scene) => {
  vi.resetModules();
  await import(scene);
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  const canvases = [document.createElement('canvas'), document.createElement('canvas')];
  try {
    canvases.forEach((canvas) => createRoot(canvas));
    expect(warn).not.toHaveBeenCalled();
  } finally {
    // No renderer was configured, so there is no WebGL resource to dispose.
    canvases.forEach((canvas) => _roots.delete(canvas));
  }
});

it('forwards unrelated diagnostics and extra details to the existing Three handler', () => {
  const handler = vi.fn();
  setConsoleFunction(handler);
  installThreeConsoleFilter();
  const output = getConsoleFunction();
  output('warn', CLOCK_DEPRECATION);
  expect(handler).not.toHaveBeenCalled();
  const details = { source: 'synthetic' };
  output('warn', 'THREE.GLTFLoader: Missing texture.', details);
  output('error', CLOCK_DEPRECATION);
  output('log', 'THREE.Test: Ready.', details);
  output('warn', CLOCK_DEPRECATION, details);
  expect(handler.mock.calls).toEqual([
    ['warn', 'THREE.GLTFLoader: Missing texture.', details],
    ['error', CLOCK_DEPRECATION],
    ['log', 'THREE.Test: Ready.', details],
    ['warn', CLOCK_DEPRECATION, details],
  ]);
});

it('preserves native console levels, arguments and Three diagnostic stacks', () => {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  const error = vi.spyOn(console, 'error').mockImplementation(() => {});
  const log = vi.spyOn(console, 'log').mockImplementation(() => {});
  installThreeConsoleFilter();
  const output = getConsoleFunction();
  const details = { source: 'synthetic' };
  output('warn', 'THREE.Test: Warning.', details);
  output('error', 'THREE.Test: Error.', details);
  output('log', 'THREE.Test: Ready.', details);
  expect(warn).toHaveBeenCalledExactlyOnceWith('THREE.Test: Warning.', details);
  expect(error).toHaveBeenCalledExactlyOnceWith('THREE.Test: Error.', details);
  expect(log).toHaveBeenCalledExactlyOnceWith('THREE.Test: Ready.', details);
  const diagnostic = new Error('Synthetic shader diagnostic');
  const stack = { isStackTrace: true, getError: vi.fn(() => diagnostic) };
  output('warn', 'THREE.Test: Shader warning.', stack);
  output('error', 'THREE.Test: Shader error.', stack);
  expect(warn).toHaveBeenLastCalledWith(diagnostic);
  expect(error).toHaveBeenLastCalledWith(diagnostic);
  expect(stack.getError.mock.calls).toEqual([
    ['THREE.Test: Shader warning.'], ['THREE.Test: Shader error.'],
  ]);
});

it('restores the existing handler during cleanup and preserves a later replacement', () => {
  const handler = vi.fn();
  setConsoleFunction(handler);
  const restore = installThreeConsoleFilter();
  expect(getConsoleFunction()).not.toBe(handler);
  restore();
  expect(getConsoleFunction()).toBe(handler);
  const restoreAgain = installThreeConsoleFilter();
  const replacement = vi.fn();
  setConsoleFunction(replacement);
  restoreAgain();
  expect(getConsoleFunction()).toBe(replacement);
});
