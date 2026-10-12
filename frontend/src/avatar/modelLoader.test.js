import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useLoader } from '@react-three/fiber';
import { TextureLoader } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { resetAvatarAssets } from './modelLoader';

vi.mock('@react-three/fiber', () => ({ useLoader: { clear: vi.fn() } }));
const appearance = { url: '/archer.glb', textures: { body: '/body.png', hair: '/hair.png', face: '/face.png' } };
beforeEach(() => useLoader.clear.mockClear());

describe('avatar failed-asset retry', () => {
  it('clears a rejected texture bundle under its actual R3F array cache key', () => {
    resetAvatarAssets(appearance, ['/hair.png']);
    expect(useLoader.clear).toHaveBeenCalledExactlyOnceWith(TextureLoader, ['/body.png', '/hair.png', '/face.png']);
  });
  it('clears a failed model independently and preserves healthy textures', () => {
    resetAvatarAssets(appearance, ['/archer.glb']);
    expect(useLoader.clear).toHaveBeenCalledExactlyOnceWith(GLTFLoader, '/archer.glb');
  });
  it('retains loaded models and textures after WebGL context loss', () => {
    resetAvatarAssets(appearance, []);
    expect(useLoader.clear).not.toHaveBeenCalled();
  });
});
