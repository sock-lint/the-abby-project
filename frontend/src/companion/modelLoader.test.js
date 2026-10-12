import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useLoader } from '@react-three/fiber';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { resetModels } from './modelLoader';

vi.mock('@react-three/fiber', () => ({ useLoader: { clear: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());
describe('Failed pet model retry', () => {
  it('clears the exact grouped creature entry as well as a rejected single load', () => {
    resetModels(['/hop.glb'], ['/idle.glb', '/hop.glb', '/left.glb']);
    expect(useLoader.clear.mock.calls).toEqual([
      [GLTFLoader, '/hop.glb'], [GLTFLoader, ['/idle.glb', '/hop.glb', '/left.glb']],
    ]);
  });
  it('preserves resolved creature takes when only the scenery failed', () => {
    resetModels(['/woodland.glb'], ['/idle.glb', '/hop.glb']);
    expect(useLoader.clear.mock.calls).toEqual([[GLTFLoader, '/woodland.glb']]);
  });
});
