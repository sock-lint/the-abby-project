import { StrictMode } from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { Group } from 'three';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CompanionScene from './CompanionScene';
import CompanionPreview from '../components/companion/CompanionPreview';

const harness = vi.hoisted(() => ({ allowed: true, instances: [], frame: null, invalidate: vi.fn(), canvas: null }));
vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }) => <div>{children}</div>,
  useFrame: (callback) => { harness.frame = callback; },
  useLoader: vi.fn(),
  useThree: (selector) => {
    const state = { invalidate: harness.invalidate, gl: { domElement: harness.canvas } };
    return selector ? selector(state) : state;
  },
}));
vi.mock('./WoodlandScene', () => ({ default: () => null, WoodlandCamera: () => null }));
vi.mock('./useSceneMotionAllowed', () => ({ default: () => harness.allowed }));
vi.mock('./appearance', () => ({
  creatureLabel: () => 'Base Chick',
  resolveAppearance: (creature) => ({
    pipeline: 'abby-assets-bird', key: creature.evolution_stage, url: `/${creature.evolution_stage}.glb`,
    rotationY: 0, manifestUrl: '/synthetic/manifest.json', manifestSha256: 'a'.repeat(64), motions: [], interactions: {},
  }),
}));
vi.mock('../components/rpg/RpgSprite', () => ({ default: () => <span /> }));
vi.mock('./sharedBirdPlayback', () => ({ createSharedBirdPlayback: vi.fn((_appearance, callbacks) => {
  const instance = { root: new Group(), callbacks, evolve: vi.fn(), reset: vi.fn(), play: vi.fn(), update: vi.fn(), dispose: vi.fn() };
  harness.instances.push(instance);
  queueMicrotask(() => { if (!instance.dispose.mock.calls.length) callbacks.onReady(); });
  return instance;
}) }));
vi.mock('./sharedRosterPlayback', () => ({ createSharedRosterPlayback: vi.fn((_appearance, callbacks) => {
  const instance = { root: new Group(), callbacks, evolve: vi.fn(), reset: vi.fn(), play: vi.fn(), update: vi.fn(), dispose: vi.fn() };
  harness.instances.push(instance);
  queueMicrotask(() => { if (!instance.dispose.mock.calls.length) callbacks.onReady(); });
  return instance;
}) }));

const appearance = { pipeline: 'abby-assets-bird', key: 'bird', rotationY: 0 };
const evolution = { id: 4, from: 'fledgling', to: 'bird' };
let media;
beforeEach(() => {
  harness.allowed = true;
  harness.instances = [];
  harness.canvas = document.createElement('canvas');
  harness.invalidate.mockClear();
  media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.spyOn(window, 'matchMedia').mockReturnValue(media);
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('Shared bird scene lifecycle', () => {
  it('retains a queued interaction when immutable roster resources replace the native instance', () => {
    const props = { appearance: { ...appearance, pipeline: 'abby-assets-roster', key: 'wolf-middle' }, animate: true,
      interaction: { id: 8, action: 'source-cast-spell' }, onReady: vi.fn(), onUnavailable: vi.fn() };
    const view = render(<CompanionScene {...props} />);
    expect(harness.instances[0].play).toHaveBeenCalledOnce();
    view.rerender(<CompanionScene {...props} appearance={{ ...props.appearance, manifestSha256: 'c'.repeat(64) }} />);
    expect(harness.instances[0].dispose).toHaveBeenCalledOnce();
    expect(harness.instances[1].play).toHaveBeenCalledExactlyOnceWith('source-cast-spell');
    view.unmount();
  });
  it('gives roster native instances the existing visibility, reduced-motion and disposal lifecycle', () => {
    harness.allowed = false;
    const props = { appearance: { ...appearance, pipeline: 'abby-assets-roster', key: 'wolf-middle' }, animate: true,
      interaction: { id: 7, action: 'source-cast-spell' }, onReady: vi.fn(), onUnavailable: vi.fn() };
    const view = render(<CompanionScene {...props} />);
    const instance = harness.instances[0];
    expect(instance.play).not.toHaveBeenCalled();
    harness.allowed = true;
    view.rerender(<CompanionScene {...props} />);
    expect(instance.play).toHaveBeenCalledExactlyOnceWith('source-cast-spell');
    harness.frame({}, 0.05);
    expect(instance.update).toHaveBeenCalledOnce();
    const changed = media.addEventListener.mock.calls.find(([event]) => event === 'change')[1];
    act(() => { media.matches = true; changed(); });
    harness.frame({}, 0.05);
    expect(instance.update).toHaveBeenCalledOnce();
    expect(instance.reset).toHaveBeenCalledOnce();
    view.unmount();
    expect(instance.dispose).toHaveBeenCalledOnce();
  });
  it('retains the native instance and consumed evolution when a stable refresh returns an equivalent appearance', () => {
    const props = { appearance: { ...appearance }, evolution, animate: true, onReady: vi.fn(), onUnavailable: vi.fn() };
    const view = render(<CompanionScene {...props} />);
    const instance = harness.instances[0];
    expect(instance.evolve).toHaveBeenCalledExactlyOnceWith('fledgling', 'bird');
    view.rerender(<CompanionScene {...props} appearance={{ ...appearance }} />);
    expect(harness.instances).toHaveLength(1);
    expect(instance.dispose).not.toHaveBeenCalled();
    expect(instance.evolve).toHaveBeenCalledOnce();
    view.unmount();
    expect(instance.dispose).toHaveBeenCalledOnce();
  });

  it('retains the actual preview instance after feeding at the same persisted stage or refreshing an evolved Bird', async () => {
    const chick = { id: 3, species: { slug: 'chick', sprite_key: 'cute-chick', name: 'Chick' }, potion: { slug: 'base' }, evolution_stage: 'chick', growth_points: 35 };
    const view = render(<CompanionPreview variant="primary" creature={chick} />);
    await waitFor(() => expect(harness.instances).toHaveLength(1));
    const fledgling = { ...chick, evolution_stage: 'fledgling', growth_points: 50 };
    view.rerender(<CompanionPreview variant="primary" creature={fledgling} />);
    await waitFor(() => expect(harness.instances).toHaveLength(2));
    const growing = harness.instances[1];
    expect(growing.evolve).toHaveBeenCalledExactlyOnceWith('chick', 'fledgling');
    view.rerender(<CompanionPreview variant="primary" creature={{ ...fledgling, growth_points: 65, last_fed_at: '2026-10-16T16:00:00Z' }} />);
    expect(harness.instances).toHaveLength(2);
    expect(growing.dispose).not.toHaveBeenCalled();
    expect(growing.evolve).toHaveBeenCalledOnce();
    const bird = { ...fledgling, evolution_stage: 'bird', growth_points: 100, evolved_to_mount: true };
    view.rerender(<CompanionPreview variant="primary" creature={bird} />);
    await waitFor(() => expect(harness.instances).toHaveLength(3));
    const evolved = harness.instances[2];
    expect(evolved.evolve).toHaveBeenCalledExactlyOnceWith('fledgling', 'bird');
    view.rerender(<CompanionPreview variant="primary" creature={{ ...bird, name: 'Peep', is_active: true }} />);
    expect(harness.instances).toHaveLength(3);
    expect(evolved.dispose).not.toHaveBeenCalled();
    expect(evolved.evolve).toHaveBeenCalledOnce();
    view.unmount();
    harness.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
  });

  it('reloads changed pinned resources but uses fresh callback props without replacing a healthy instance', () => {
    const ready = vi.fn(), latestReady = vi.fn();
    const props = { appearance, animate: true, onReady: ready, onUnavailable: vi.fn() };
    const view = render(<CompanionScene {...props} />);
    view.rerender(<CompanionScene {...props} onReady={latestReady} />);
    expect(harness.instances).toHaveLength(1);
    act(() => harness.instances[0].callbacks.onReady());
    expect(latestReady).toHaveBeenCalledOnce();
    expect(ready).not.toHaveBeenCalled();
    view.rerender(<CompanionScene {...props} appearance={{ ...appearance, manifestSha256: 'b'.repeat(64) }} />);
    expect(harness.instances).toHaveLength(2);
    expect(harness.instances[0].dispose).toHaveBeenCalledOnce();
    view.unmount();
  });

  it('queues a motion requested below an offscreen canvas until the native scene becomes visible', () => {
    harness.allowed = false;
    const props = { appearance, interaction: { id: 2, action: 'source-attack' }, animate: true, onReady: vi.fn(), onUnavailable: vi.fn() };
    const view = render(<CompanionScene {...props} />);
    const instance = harness.instances[0];
    expect(instance.play).not.toHaveBeenCalled();
    harness.allowed = true;
    view.rerender(<CompanionScene {...props} />);
    expect(instance.play).toHaveBeenCalledExactlyOnceWith('source-attack');
    harness.allowed = false;
    view.rerender(<CompanionScene {...props} />);
    harness.allowed = true;
    view.rerender(<CompanionScene {...props} />);
    expect(instance.play).toHaveBeenCalledOnce();
    view.unmount();
  });

  it('waits for initial visibility, then plays a confirmed evolution once and pauses its clock when hidden', () => {
    harness.allowed = false;
    const props = { appearance, evolution, animate: true, onReady: vi.fn(), onUnavailable: vi.fn() };
    const view = render(<CompanionScene {...props} />);
    const instance = harness.instances[0];
    expect(instance.evolve).not.toHaveBeenCalled();
    act(() => harness.frame({}, 1));
    expect(instance.update).not.toHaveBeenCalled();
    harness.allowed = true;
    view.rerender(<CompanionScene {...props} />);
    expect(instance.evolve).toHaveBeenCalledExactlyOnceWith('fledgling', 'bird');
    act(() => harness.frame({}, 0.05));
    expect(instance.update).toHaveBeenCalledWith(0.05, { active: true, paused: false });
    harness.allowed = false;
    view.rerender(<CompanionScene {...props} />);
    instance.update.mockClear();
    act(() => harness.frame({}, 1));
    expect(instance.update).not.toHaveBeenCalled();
    view.unmount();
    expect(instance.dispose).toHaveBeenCalledOnce();
  });

  it('settles directly on destination idle for reduced motion and does not replay the receipt when preferences change', () => {
    media.matches = true;
    const props = { appearance, evolution, animate: true, onReady: vi.fn(), onUnavailable: vi.fn() };
    const view = render(<CompanionScene {...props} />);
    const instance = harness.instances[0];
    expect(instance.reset).toHaveBeenCalled();
    expect(instance.evolve).not.toHaveBeenCalled();
    media.matches = false;
    act(() => media.addEventListener.mock.calls[0][1]());
    expect(instance.evolve).not.toHaveBeenCalled();
    view.unmount();
    expect(media.removeEventListener).toHaveBeenCalledWith('change', expect.any(Function));
  });

  it('cancels in-flight evolution when animation is disabled and skips an initial disabled receipt', () => {
    const props = { appearance, evolution, animate: true, onReady: vi.fn(), onUnavailable: vi.fn() };
    const view = render(<CompanionScene {...props} />);
    const instance = harness.instances[0];
    expect(instance.evolve).toHaveBeenCalledOnce();
    view.rerender(<CompanionScene {...props} animate={false} />);
    expect(instance.reset).toHaveBeenCalledOnce();
    view.rerender(<CompanionScene {...props} />);
    expect(instance.evolve).toHaveBeenCalledOnce();
    view.unmount();
    render(<CompanionScene {...props} animate={false} />);
    expect(harness.instances[1].evolve).not.toHaveBeenCalled();
    expect(harness.instances[1].reset).toHaveBeenCalledOnce();
  });

  it('disposes StrictMode abandoned instances and preserves the committed evolution receipt', () => {
    const props = { appearance, evolution, animate: true, onReady: vi.fn(), onUnavailable: vi.fn() };
    const view = render(<StrictMode><CompanionScene {...props} /></StrictMode>);
    expect(harness.instances).toHaveLength(2);
    expect(harness.instances[0].dispose).toHaveBeenCalledOnce();
    expect(harness.instances[1].dispose).not.toHaveBeenCalled();
    expect(harness.instances[1].evolve).toHaveBeenCalledExactlyOnceWith('fledgling', 'bird');
    view.unmount();
    expect(harness.instances[1].dispose).toHaveBeenCalledOnce();
  });
});
