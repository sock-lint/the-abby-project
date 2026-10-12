import { describe, expect, it, vi } from 'vitest';
import { AnimationClip, Bone, BoxGeometry, Float32BufferAttribute, Group, Mesh, MeshBasicMaterial, NumberKeyframeTrack, Skeleton, SkinnedMesh, Uint16BufferAttribute } from 'three';
import { createCreaturePlayback } from './creaturePlayback';

function take(name, height = 1) {
  const scene = new Group();
  const head = new Mesh(new BoxGeometry(1, height, 1), new MeshBasicMaterial());
  head.name = 'Head';
  scene.add(head);
  return { scene, animations: [new AnimationClip(name, 1, [new NumberKeyframeTrack('Head.rotation[z]', [0, 0.5, 1], [0, 0.4, 0])])] };
}
const appearance = { url: '/idle.glb', idleClip: 'Idle', interactions: { play: { url: '/play.glb', clip: 'Hop' }, left: { url: '/left.glb', clip: 'Turn' } } };

describe('Supplied pet take playback', () => {
  it('plays a bounded burst of the supplied loop, then restores idle and calls completion once', () => {
    const idle = take('Idle');
    const play = take('Hop', 2);
    const playback = createCreaturePlayback({ idle, play }, appearance);
    const resting = playback.root.children[0];
    const completed = vi.fn();
    expect(playback.play('play', completed)).toBe(true);
    expect(playback.root.children[0]).not.toBe(resting);
    // One shared idle framing keeps differing bind-pose heights from resizing.
    expect(playback.root.children[0].scale.y).toBe(resting.scale.y);
    playback.update(0.5);
    expect(playback.playing).toBe(true); // long suspended frames are bounded
    for (let frame = 0; frame < 85; frame += 1) playback.update(0.05);
    expect(playback.root.children[0]).toBe(resting);
    expect(completed).toHaveBeenCalledTimes(1);
    expect(playback.playing).toBe(false);
    expect(play.scene.children[0].rotation.z).toBe(0);
    playback.dispose();
  });

  it('reverses authored turns, safely replaces rapid inputs and cancels on reset', () => {
    const playback = createCreaturePlayback({ idle: take('Idle'), left: take('Turn'), play: take('Hop') }, appearance);
    const interrupted = vi.fn();
    const completed = vi.fn();
    playback.play('play', interrupted);
    playback.play('left', completed);
    for (let frame = 0; frame < 25; frame += 1) playback.update(0.05);
    expect(playback.playing).toBe(true);
    for (let frame = 0; frame < 25; frame += 1) playback.update(0.05);
    expect(completed).toHaveBeenCalledTimes(1);
    expect(interrupted).not.toHaveBeenCalled();
    playback.play('play', interrupted);
    playback.reset();
    for (let frame = 0; frame < 25; frame += 1) playback.update(0.05);
    expect(interrupted).not.toHaveBeenCalled();
    expect(playback.play('unknown')).toBe(false);
    playback.dispose();
    playback.reset(); // React StrictMode's effect cleanup/setup can replay.
    expect(playback.root.children).toHaveLength(1);
  });

  it('rejects unverified clip names rather than silently presenting a different animation', () => {
    expect(() => createCreaturePlayback({ idle: take('Idle'), play: take('Wrong') }, appearance)).toThrow('/play.glb is missing its verified clip');
  });

  it('releases private skeleton textures across mounts without disposing cached source resources', () => {
    const bone = new Bone();
    const geometry = new BoxGeometry(1, 1, 1);
    const count = geometry.attributes.position.count;
    geometry.setAttribute('skinIndex', new Uint16BufferAttribute(new Array(count * 4).fill(0), 4));
    geometry.setAttribute('skinWeight', new Float32BufferAttribute(Array.from({ length: count }, () => [1, 0, 0, 0]).flat(), 4));
    const mesh = new SkinnedMesh(geometry, new MeshBasicMaterial());
    mesh.add(bone);
    mesh.bind(new Skeleton([bone]));
    mesh.skeleton.computeBoneTexture();
    const sourceTexture = mesh.skeleton.boneTexture;
    const scene = new Group();
    scene.add(mesh);
    const playback = createCreaturePlayback({ idle: { scene, animations: [new AnimationClip('Idle', 1, [])] } }, appearance);
    let privateSkeleton;
    playback.root.traverse((node) => { if (node.skeleton) privateSkeleton = node.skeleton; });
    privateSkeleton.computeBoneTexture();
    const released = vi.spyOn(privateSkeleton.boneTexture, 'dispose');
    const sourceReleased = vi.spyOn(sourceTexture, 'dispose');
    const geometryReleased = vi.spyOn(geometry, 'dispose');
    playback.dispose();
    expect(released).toHaveBeenCalledOnce();
    expect(sourceReleased).not.toHaveBeenCalled();
    expect(geometryReleased).not.toHaveBeenCalled();
    expect(privateSkeleton.boneTexture).toBeNull();
    playback.reset();
    privateSkeleton.computeBoneTexture();
    expect(privateSkeleton.boneTexture).not.toBeNull();
    playback.dispose();
    mesh.skeleton.dispose();
  });
});
