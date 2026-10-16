import { StrictMode } from 'react';
import { act, render } from '@testing-library/react';
import { Group } from 'three';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CompanionScene from './CompanionScene';

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
vi.mock('./sharedBirdPlayback', () => ({ createSharedBirdPlayback: vi.fn((_appearance, callbacks) => {
  const instance = { root: new Group(), evolve: vi.fn(), reset: vi.fn(), play: vi.fn(), update: vi.fn(), dispose: vi.fn() };
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
