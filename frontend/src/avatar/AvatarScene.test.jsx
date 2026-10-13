import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { Group, Mesh, MeshStandardMaterial, PerspectiveCamera, Texture } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import AvatarScene from './AvatarScene';

const harness = vi.hoisted(() => ({ canvas: null, camera: null, gltf: null, textures: null, frame: null, invalidate: null, reactionRoot: null }));
vi.mock('./avatarReactions', async (importOriginal) => {
  const actual = await importOriginal();
  return { createAvatarReactions: (root) => {
    harness.reactionRoot = root;
    return actual.createAvatarReactions(root);
  } };
});
vi.mock('@react-three/fiber', () => ({
  // Installed R3F mounts fallback React children inside <canvas>, including
  // when WebGL works. A fallback effect must not signal renderer failure.
  Canvas: ({ children, fallback }) => <div><canvas>{fallback}</canvas>{children}</div>,
  useFrame: (callback) => { harness.frame = callback; },
  useLoader: (Loader) => Loader === GLTFLoader ? harness.gltf : harness.textures,
  useThree: (selector) => selector({ camera: harness.camera, invalidate: harness.invalidate, gl: { domElement: harness.canvas } }),
}));

const appearance = {
  url: '/synthetic-archer.glb', idleClip: null, rotationY: 0,
  parts: { body: 'Body', head: 'Head', face: 'Face', hair: { 'hair-01': 'Hair 01', 'hair-02': 'Hair 02' } },
  hairStyle: 'hair-01', textures: { body: '/body.png', hair: '/hair.png', face: '/face.png' },
};

beforeEach(() => {
  harness.canvas = document.createElement('canvas');
  harness.camera = new PerspectiveCamera();
  harness.camera.position.set(0, 1.05, 3.7);
  harness.invalidate = vi.fn();
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
  it('stops an active reaction when motion is paused and does not replay it on resume', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const props = { appearance, onReady: vi.fn(), onUnavailable: vi.fn(), interaction: { id: 1, action: 'hop' } };
    const { rerender } = render(<AvatarScene {...props} motionAllowed />);
    act(() => harness.frame({}, 0.05));
    expect(harness.reactionRoot.position.y).toBeGreaterThan(0);
    rerender(<AvatarScene {...props} motionAllowed={false} />);
    expect(harness.reactionRoot.position.y).toBe(0);
    rerender(<AvatarScene {...props} motionAllowed />);
    harness.invalidate.mockClear();
    act(() => harness.frame({}, 0.05));
    expect(harness.reactionRoot.position.y).toBe(0);
    expect(harness.invalidate).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('finishes a reaction and stops requesting animation frames', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<AvatarScene appearance={appearance} onReady={() => {}} onUnavailable={() => {}} interaction={{ id: 1, action: 'twirl' }} />);
    act(() => harness.frame({}, 0.05));
    expect(harness.reactionRoot.rotation.y).toBeGreaterThan(0);
    act(() => { for (let frame = 0; frame < 30; frame++) harness.frame({}, 0.05); });
    expect(harness.reactionRoot.rotation.y).toBe(0);
    harness.invalidate.mockClear();
    act(() => harness.frame({}, 0.05));
    expect(harness.invalidate).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('applies keyboard camera commands, resets the view and restores canvas touch handling on unmount', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    harness.canvas.style.touchAction = 'pan-y';
    const props = { appearance, onReady: vi.fn(), onUnavailable: vi.fn() };
    const front = harness.camera.position.clone();
    const { rerender, unmount } = render(<AvatarScene {...props} />);
    expect(harness.canvas.style.touchAction).toBe('pinch-zoom');
    rerender(<AvatarScene {...props} cameraOrbit={{ id: 1, horizontal: 1, vertical: 0 }} />);
    expect(harness.camera.position.x).not.toBeCloseTo(front.x);
    rerender(<AvatarScene {...props} cameraOrbit={{ id: 1, horizontal: 1, vertical: 0 }} cameraReset={1} />);
    expect(harness.camera.position.distanceTo(front)).toBeLessThan(1e-10);
    unmount();
    expect(harness.canvas.style.touchAction).toBe('pan-y');
    consoleError.mockRestore();
  });

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
