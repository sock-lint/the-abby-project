import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StrictMode, useRef } from 'react';
import { act, render, screen } from '@testing-library/react';
import { AnimationClip, AnimationMixer, Bone, BoxGeometry, Float32BufferAttribute, Group, Mesh, MeshStandardMaterial, NumberKeyframeTrack, PerspectiveCamera, Skeleton, SkinnedMesh, Texture, Uint16BufferAttribute, Vector3 } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import AvatarScene from './AvatarScene';
import useSceneMotionAllowed from '../companion/useSceneMotionAllowed';

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
    const part = new Mesh(new BoxGeometry(1, 1, 1), new MeshStandardMaterial());
    part.name = name;
    scene.add(part);
  }
  harness.gltf = { scene, animations: [] };
  harness.textures = [new Texture(), new Texture(), new Texture()];
});

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function animatedArcher() {
  const geometry = new BoxGeometry(1, 1, 1);
  const count = geometry.attributes.position.count;
  geometry.setAttribute('skinIndex', new Uint16BufferAttribute(new Array(count * 4).fill(0), 4));
  geometry.setAttribute('skinWeight', new Float32BufferAttribute(Array.from({ length: count }, () => [1, 0, 0, 0]).flat(), 4));
  const bone = new Bone();
  bone.name = 'Archer_Root';
  const body = new SkinnedMesh(geometry, new MeshStandardMaterial());
  body.name = 'Body';
  body.add(bone);
  body.bind(new Skeleton([bone]));
  harness.gltf.scene.remove(harness.gltf.scene.getObjectByName('Body'));
  harness.gltf.scene.add(body);
  harness.gltf.animations = [new AnimationClip('Idle', 1, [new NumberKeyframeTrack('Archer_Root.rotation[z]', [0, 0.5, 1], [0, 0.3, 0])])];
  return body;
}

function MotionScene(props) {
  const ref = useRef(null);
  const motionAllowed = useSceneMotionAllowed(ref);
  return <div ref={ref} data-testid="motion-stage"><AvatarScene {...props} motionAllowed={motionAllowed} /></div>;
}

const wardrobeParts = {
  hair_for_hat: 'Hat hair',
  headwear: { 'crown-eve': 'Crown', 'hood-mystical': 'Hood' },
  mask: { 'mask-undercover': 'Mask' },
  bow: { 'bow-greenhorn': 'Greenhorn', 'bow-vines': 'Vines', 'bow-myth': 'Myth' },
  quiver: { 'quiver-angel': 'Angel', 'quiver-rook': 'Rook', 'quiver-tale': 'Tale' },
};
function addWardrobe() {
  for (const name of [wardrobeParts.hair_for_hat, ...['headwear', 'mask', 'bow', 'quiver'].flatMap((slot) => Object.values(wardrobeParts[slot]))]) {
    const module = new Mesh(new BoxGeometry(0.2, 0.2, 0.2), new MeshStandardMaterial());
    module.name = name;
    harness.gltf.scene.add(module);
  }
}
function withWardrobe(selected = {}) {
  const wardrobe = { headwear: 'none', mask: 'none', bow: 'none', quiver: 'none', ...selected };
  const textures = { ...appearance.textures, ...Object.fromEntries(Object.entries(wardrobe).filter(([, style]) => style !== 'none').map(([slot]) => [slot, `/${slot}.png`])) };
  harness.textures = Object.keys(textures).map(() => new Texture());
  return { ...appearance, parts: { ...appearance.parts, wardrobe: wardrobeParts }, wardrobe, textures };
}

describe('AvatarScene lifecycle', () => {
  it.each(['none', 'crown-eve', 'hood-mystical'])('selects %s independently and uses hat hair only under a hood', (headwear) => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    addWardrobe();
    const selected = withWardrobe({ headwear, mask: 'mask-undercover', bow: 'bow-vines', quiver: 'quiver-angel' });
    render(<AvatarScene appearance={selected} onReady={() => {}} onUnavailable={() => {}} />);
    const root = harness.reactionRoot;
    for (const [slot, options] of Object.entries(wardrobeParts).filter(([slot]) => slot !== 'hair_for_hat')) {
      for (const [style, name] of Object.entries(options)) {
        expect(root.getObjectByName(name).visible).toBe(selected.wardrobe[slot] === style);
        expect(harness.gltf.scene.getObjectByName(name).visible).toBe(true);
      }
    }
    expect(root.getObjectByName('Hat hair').visible).toBe(headwear === 'hood-mystical');
    expect(root.getObjectByName('Hair 01').visible).toBe(headwear !== 'hood-mystical');
    expect(root.getObjectByName('Hair 02').visible).toBe(false);
    if (headwear === 'hood-mystical') expect(root.getObjectByName('Hat hair').material.map).toBe(root.getObjectByName('Hair 01').material.map);
    expect(root.getObjectByName('Vines').material.map).not.toBe(root.getObjectByName('Body').material.map);
  });

  it('frames the original identity independently of hidden oversized wardrobe meshes', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<AvatarScene appearance={appearance} onReady={() => {}} onUnavailable={() => {}} />);
    const originalScene = harness.reactionRoot.children[0];
    const originalScale = originalScene.scale.x;
    const originalPosition = originalScene.position.toArray();
    addWardrobe();
    harness.gltf.scene.getObjectByName('Tale').position.y = 50;
    render(<AvatarScene appearance={withWardrobe()} onReady={() => {}} onUnavailable={() => {}} />);
    const scene = harness.reactionRoot.children[0];
    expect(scene.scale.x).toBeCloseTo(originalScale);
    expect(scene.position.toArray()).toEqual(originalPosition);
    expect(scene.getObjectByName('Tale').visible).toBe(false);
  });

  it('keeps a supplied rigid bow parented to its moving source bone and disposes only private wardrobe textures and materials', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const sourceBody = animatedArcher();
    addWardrobe();
    const sourceBow = harness.gltf.scene.getObjectByName('Vines');
    sourceBow.position.set(0.75, 0, 0);
    sourceBody.skeleton.bones[0].add(sourceBow);
    const sourceMaterialDisposed = vi.spyOn(sourceBow.material, 'dispose');
    const sourceGeometryDisposed = vi.spyOn(sourceBow.geometry, 'dispose');
    const selected = withWardrobe({ bow: 'bow-vines' });
    const sourceTextureDisposed = harness.textures.map((map) => vi.spyOn(map, 'dispose'));
    const { unmount } = render(<AvatarScene appearance={{ ...selected, idleClip: 'Idle' }} onReady={() => {}} onUnavailable={() => {}} />);
    const bow = harness.reactionRoot.getObjectByName('Vines');
    const before = bow.getWorldPosition(new Vector3()).clone();
    act(() => harness.frame({}, 0.05));
    expect(bow.parent.name).toBe('Archer_Root');
    expect(bow.getWorldPosition(new Vector3()).distanceTo(before)).toBeGreaterThan(0.001);
    expect(sourceBow.parent.rotation.z).toBe(0);
    expect(bow.position.toArray()).toEqual(sourceBow.position.toArray());
    const materialDisposed = vi.spyOn(bow.material, 'dispose');
    const textureDisposed = vi.spyOn(bow.material.map, 'dispose');
    unmount();
    expect(materialDisposed).toHaveBeenCalledOnce();
    expect(textureDisposed).toHaveBeenCalledOnce();
    expect(sourceMaterialDisposed).not.toHaveBeenCalled();
    expect(sourceGeometryDisposed).not.toHaveBeenCalled();
    sourceTextureDisposed.forEach((dispose) => expect(dispose).not.toHaveBeenCalled());
  });

  it('rejects incomplete wardrobe geometry before cloning cached textures or signaling readiness', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    addWardrobe();
    harness.gltf.scene.remove(harness.gltf.scene.getObjectByName('Crown'));
    const selected = withWardrobe();
    const clone = vi.spyOn(harness.textures[0], 'clone');
    const onReady = vi.fn();
    expect(() => render(<AvatarScene appearance={selected} onReady={onReady} onUnavailable={() => {}} />)).toThrow('missing Crown');
    expect(clone).not.toHaveBeenCalled();
    expect(onReady).not.toHaveBeenCalled();
  });

  it('attaches the animated model to the committed root under StrictMode double memo invocation', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    animatedArcher();
    const { container } = render(<StrictMode><AvatarScene appearance={{ ...appearance, idleClip: 'Idle' }} onReady={() => {}} onUnavailable={() => {}} /></StrictMode>);
    // The mocked canvas renders the primitive as a DOM element. Inspect its
    // actual committed object, rather than the discarded second memo result.
    const primitive = container.querySelector('primitive');
    const propsKey = Object.keys(primitive).find((key) => key.startsWith('__reactProps'));
    const committedRoot = primitive[propsKey].object;
    expect(committedRoot.getObjectByName('Body')).toBeDefined();
    expect(committedRoot.children).toHaveLength(1);
    act(() => harness.frame({}, 0.05));
    expect(committedRoot.getObjectByName('Archer_Root').rotation.z).toBeGreaterThan(0);
  });

  it.each(['head-01', 'head-02'])('shows only the selected %s without changing cached head geometry', (headStyle) => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const rounded = new Mesh(undefined, new MeshStandardMaterial());
    rounded.name = 'Head Rounded';
    harness.gltf.scene.add(rounded);
    render(<AvatarScene appearance={{ ...appearance, headStyle,
      parts: { ...appearance.parts, head: { 'head-01': 'Head Rounded', 'head-02': 'Head' } } }} onReady={() => {}} onUnavailable={() => {}} />);
    const privateRounded = harness.reactionRoot.getObjectByName('Head Rounded');
    const privatePointed = harness.reactionRoot.getObjectByName('Head');
    expect(privateRounded.visible).toBe(headStyle === 'head-01');
    expect(privatePointed.visible).toBe(headStyle === 'head-02');
    expect(privateRounded.material.map).toBe(harness.reactionRoot.getObjectByName('Body').material.map);
    expect(privatePointed.material.map).toBe(privateRounded.material.map);
    expect(rounded.visible).toBe(true);
    expect(harness.gltf.scene.getObjectByName('Head').visible).toBe(true);
  });
  it('animates the private supplied skeleton and skin while leaving cached source bones at rest', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const source = animatedArcher();
    render(<AvatarScene appearance={{ ...appearance, idleClip: 'Idle' }} onReady={() => {}} onUnavailable={() => {}} />);
    const privateBody = harness.reactionRoot.getObjectByName('Body');
    const privateBone = privateBody.skeleton.bones[0];
    expect(privateBone).not.toBe(source.skeleton.bones[0]);
    const restingVertex = privateBody.getVertexPosition(0, new Vector3()).clone();
    act(() => harness.frame({}, 0.05));
    privateBody.updateMatrixWorld(true);
    privateBody.skeleton.update();
    expect(privateBone.rotation.z).toBeCloseTo(0.03);
    expect(privateBody.getVertexPosition(0, new Vector3()).distanceTo(restingVertex)).toBeGreaterThan(0);
    expect(source.skeleton.bones[0].rotation.z).toBe(0);
    // A long suspended frame cannot leap ahead through the Idle loop.
    act(() => harness.frame({}, 30));
    expect(privateBone.rotation.z).toBeCloseTo(0.06);
  });

  it('pauses the actual Idle for offscreen, hidden documents and reduced motion, then resumes without time jumps', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    animatedArcher();
    let observe;
    let hidden = false;
    const media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
    vi.spyOn(window, 'matchMedia').mockReturnValue(media);
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback) { observe = callback; }
      observe() {}
      disconnect() {}
    });
    render(<MotionScene appearance={{ ...appearance, idleClip: 'Idle' }} onReady={() => {}} onUnavailable={() => {}} />);
    const stage = screen.getByTestId('motion-stage');
    const bone = harness.reactionRoot.getObjectByName('Archer_Root');
    const visible = (isIntersecting) => act(() => observe([{ target: stage, isIntersecting }]));
    const frame = () => act(() => harness.frame({}, 0.05));
    frame();
    expect(bone.rotation.z).toBeCloseTo(0);
    visible(true);
    frame();
    expect(bone.rotation.z).toBeCloseTo(0.03);
    visible(false);
    harness.invalidate.mockClear();
    frame();
    expect(bone.rotation.z).toBeCloseTo(0.03);
    expect(harness.invalidate).not.toHaveBeenCalled();
    visible(true);
    hidden = true;
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    frame();
    expect(bone.rotation.z).toBeCloseTo(0.03);
    hidden = false;
    media.matches = true;
    act(() => media.addEventListener.mock.calls[0][1]());
    frame();
    expect(bone.rotation.z).toBeCloseTo(0.03);
    media.matches = false;
    act(() => media.addEventListener.mock.calls[0][1]());
    frame();
    expect(bone.rotation.z).toBeCloseTo(0.06);
  });

  it('stops and uncaches Idle and disposes private materials, textures and skeletons across remounts', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const source = animatedArcher();
    source.skeleton.computeBoneTexture();
    const sourceDisposed = vi.spyOn(source.skeleton.boneTexture, 'dispose');
    const sourceMaterialDisposed = vi.spyOn(source.material, 'dispose');
    const sourceGeometryDisposed = vi.spyOn(source.geometry, 'dispose');
    const sourceMapsDisposed = harness.textures.map((map) => vi.spyOn(map, 'dispose'));
    const stopped = vi.spyOn(AnimationMixer.prototype, 'stopAllAction');
    const uncached = vi.spyOn(AnimationMixer.prototype, 'uncacheRoot');
    const props = { appearance: { ...appearance, idleClip: 'Idle' }, onReady: vi.fn(), onUnavailable: vi.fn() };
    const { unmount } = render(<AvatarScene {...props} />);
    const privateScene = harness.reactionRoot.children[0];
    const privateBody = privateScene.getObjectByName('Body');
    privateBody.skeleton.computeBoneTexture();
    const privateBoneTextureDisposed = vi.spyOn(privateBody.skeleton.boneTexture, 'dispose');
    const privateMaterialDisposed = vi.spyOn(privateBody.material, 'dispose');
    const privateMapDisposed = vi.spyOn(privateBody.material.map, 'dispose');
    act(() => harness.frame({}, 0.05));
    unmount();
    expect(stopped).toHaveBeenCalledOnce();
    expect(uncached).toHaveBeenCalledExactlyOnceWith(privateScene);
    expect(privateBoneTextureDisposed).toHaveBeenCalledOnce();
    expect(privateMaterialDisposed).toHaveBeenCalledOnce();
    expect(privateMapDisposed).toHaveBeenCalledOnce();
    expect(privateBody.skeleton.boneTexture).toBeNull();
    expect(sourceDisposed).not.toHaveBeenCalled();
    expect(sourceMaterialDisposed).not.toHaveBeenCalled();
    expect(sourceGeometryDisposed).not.toHaveBeenCalled();
    sourceMapsDisposed.forEach((spy) => expect(spy).not.toHaveBeenCalled());
    render(<AvatarScene {...props} />);
    const resumedBone = harness.reactionRoot.getObjectByName('Archer_Root');
    expect(resumedBone.rotation.z).toBeCloseTo(0);
    act(() => harness.frame({}, 0.05));
    expect(resumedBone.rotation.z).toBeCloseTo(0.03);
  });

  it('keeps the cached source geometry intact and releases the privately prepared extra-influence geometry', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const source = animatedArcher();
    const count = source.geometry.attributes.position.count;
    source.geometry.setAttribute('joints_1', new Uint16BufferAttribute(new Array(count * 4).fill(0), 4));
    source.geometry.setAttribute('weights_1', new Float32BufferAttribute(Array.from({ length: count }, () => [0.2, 0, 0, 0]).flat(), 4));
    const originalWeights = [...source.geometry.attributes.skinWeight.array];
    const sourceDisposed = vi.spyOn(source.geometry, 'dispose');
    const { unmount } = render(<AvatarScene appearance={{ ...appearance, idleClip: 'Idle' }} onReady={() => {}} onUnavailable={() => {}} />);
    const privateBody = harness.reactionRoot.getObjectByName('Body');
    expect(privateBody.geometry).not.toBe(source.geometry);
    expect(privateBody.geometry.attributes.skinWeight.getX(0)).toBeCloseTo(0.8);
    expect(privateBody.material.customProgramCacheKey()).toContain('abby-eight-influences-v1');
    const privateDisposed = vi.spyOn(privateBody.geometry, 'dispose');
    unmount();
    expect(privateDisposed).toHaveBeenCalledOnce();
    expect(sourceDisposed).not.toHaveBeenCalled();
    expect([...source.geometry.attributes.skinWeight.array]).toEqual(originalWeights);
  });

  it('rejects a missing accepted Idle before allocating private model resources or reporting ready', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const clonedTexture = vi.spyOn(Texture.prototype, 'clone');
    const onReady = vi.fn();
    expect(() => render(<AvatarScene appearance={{ ...appearance, idleClip: 'Idle' }} onReady={onReady} onUnavailable={() => {}} />)).toThrow('missing its reviewed idle clip');
    expect(onReady).not.toHaveBeenCalled();
    expect(clonedTexture).not.toHaveBeenCalled();
  });

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
