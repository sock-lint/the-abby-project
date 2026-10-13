import { describe, expect, it } from 'vitest';
import { Group, Mesh } from 'three';
import { createAvatarReactions } from './avatarReactions';

function fixture() {
  const root = new Group();
  root.position.set(1, 2, 3);
  root.rotation.set(0, 0.4, 0);
  const part = new Mesh();
  part.position.set(0, 0.8, 0);
  root.add(part);
  const pose = { position: root.position.toArray(), rotation: root.rotation.toArray() };
  return { root, part, pose, playback: createAvatarReactions(root) };
}

describe('Whole avatar reactions', () => {
  it.each(['hop', 'twirl', 'bow'])('moves the complete avatar for %s and returns exactly to its rest pose', (action) => {
    const { root, part, pose, playback } = fixture();
    const partPosition = part.position.toArray();
    playback.play(action);
    for (let frame = 0; frame < 8; frame++) playback.update(0.05);
    expect(playback.playing).toBe(true);
    if (action === 'hop') expect(root.position.y).toBeGreaterThan(pose.position[1]);
    if (action === 'twirl') expect(root.rotation.y).toBeGreaterThan(pose.rotation[1]);
    if (action === 'bow') expect(root.rotation.x).toBeGreaterThan(0);
    expect(part.position.toArray()).toEqual(partPosition);
    for (let frame = 0; frame < 30; frame++) playback.update(0.05);
    expect(playback.playing).toBe(false);
    expect(root.position.toArray()).toEqual(pose.position);
    expect(root.rotation.toArray()).toEqual(pose.rotation);
    playback.update(0.05);
    expect(root.position.toArray()).toEqual(pose.position);
  });

  it('repeated taps replace the prior reaction without accumulating a transform', () => {
    const { root, pose, playback } = fixture();
    playback.play('hop');
    playback.update(0.05);
    playback.play('twirl');
    expect(root.position.toArray()).toEqual(pose.position);
    playback.update(0.05);
    playback.reset();
    expect(root.rotation.toArray()).toEqual(pose.rotation);
    expect(playback.playing).toBe(false);
    expect(playback.play('unknown')).toBe(false);
  });

  it('bounds a suspended frame and rejects invalid elapsed time', () => {
    const { root, playback } = fixture();
    playback.play('hop');
    playback.update(30);
    expect(playback.playing).toBe(true);
    expect(root.position.y).toBeLessThan(2.1);
    const position = root.position.toArray();
    playback.update(Number.NaN);
    expect(root.position.toArray()).toEqual(position);
  });
});
