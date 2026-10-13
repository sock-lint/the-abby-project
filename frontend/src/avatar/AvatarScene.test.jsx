import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { Group, Mesh, MeshStandardMaterial, Texture } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import AvatarScene from './AvatarScene';

const harness = vi.hoisted(() => ({ canvas: null, gltf: null, textures: null }));
vi.mock('@react-three/fiber', () => ({
  // Installed R3F mounts fallback React children inside <canvas>, including
  // when WebGL works. A fallback effect must not signal renderer failure.
  Canvas: ({ children, fallback }) => <div><canvas>{fallback}</canvas>{children}</div>,
  useFrame: vi.fn(),
  useLoader: (Loader) => Loader === GLTFLoader ? harness.gltf : harness.textures,
  useThree: (selector) => selector({ invalidate: () => {}, gl: { domElement: harness.canvas } }),
}));

const appearance = {
  url: '/synthetic-archer.glb', idleClip: null, rotationY: 0,
  parts: { body: 'Body', head: 'Head', face: 'Face', hair: { 'hair-01': 'Hair 01', 'hair-02': 'Hair 02' } },
  hairStyle: 'hair-01', textures: { body: '/body.png', hair: '/hair.png', face: '/face.png' },
};

beforeEach(() => {
  harness.canvas = document.createElement('canvas');
  const scene = new Group();
  for (const name of ['Body', 'Head', 'Face', 'Hair 01', 'Hair 02']) {
    const part = new Mesh(undefined, new MeshStandardMaterial());
    part.name = name;
    scene.add(part);
  }
  harness.gltf = { scene, animations: [] };
  harness.textures = [new Texture(), new Texture(), new Texture()];
});

describe('AvatarScene lifecycle', () => {
  it('keeps a healthy avatar when Canvas mounts its fallback children', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const onReady = vi.fn();
    const onUnavailable = vi.fn();
    render(<AvatarScene appearance={appearance} onReady={onReady} onUnavailable={onUnavailable} />);
    expect(screen.getByText('Your browser could not display the character.')).toBeInTheDocument();
    expect(onReady).toHaveBeenCalled();
    expect(onUnavailable).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('reports actual context loss and removes the handler when leaving', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const onUnavailable = vi.fn();
    const { unmount } = render(<AvatarScene appearance={appearance} onReady={() => {}} onUnavailable={onUnavailable} />);
    const lost = new Event('webglcontextlost', { cancelable: true });
    act(() => harness.canvas.dispatchEvent(lost));
    expect(lost.defaultPrevented).toBe(true);
    expect(onUnavailable).toHaveBeenCalledTimes(1);
    unmount();
    act(() => harness.canvas.dispatchEvent(new Event('webglcontextlost', { cancelable: true })));
    expect(onUnavailable).toHaveBeenCalledTimes(1);
    consoleError.mockRestore();
  });
});
