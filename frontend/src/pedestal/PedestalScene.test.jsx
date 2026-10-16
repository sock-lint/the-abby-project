import { StrictMode } from 'react';
import { act, render } from '@testing-library/react';
import { Group } from 'three';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PedestalScene from './PedestalScene';

const harness = vi.hoisted(() => ({ instances: [], frame: null, invalidate: vi.fn(), canvas: null, props: null }));
vi.mock('@react-three/fiber', () => ({
  // R3F mounts fallback as the HTML canvas's children, including on a healthy
  // renderer. It is browser fallback markup rather than an error callback.
  Canvas: ({ children, ...props }) => { harness.props = props; return <div><canvas>{props.fallback}</canvas>{children}</div>; },
  useFrame: (callback) => { harness.frame = callback; },
  useThree: (selector) => selector({ invalidate: harness.invalidate, gl: { domElement: harness.canvas } }),
}));
vi.mock('./pedestalPlayback', () => ({ createPedestalPlayback: vi.fn((_staged, callbacks) => {
  const instance = { root: new Group(), callbacks, update: vi.fn(), dispose: vi.fn() };
  harness.instances.push(instance);
  return instance;
}) }));

const staged = {
  manifestUrl: '/synthetic-manifest.json', manifestSha256: 'a'.repeat(64),
  release: { files: [{ path: 'objects/synthetic.glb' }] }, resolveUrl: () => '/synthetic.glb',
};
beforeEach(() => {
  harness.instances = [];
  harness.frame = null;
  harness.invalidate.mockClear();
  harness.canvas = document.createElement('canvas');
  harness.props = null;
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('native pedestal scene lifecycle', () => {
  it('uses native-metre camera framing, demand rendering and a bounded device pixel ratio', () => {
    const view = render(<PedestalScene staged={staged} onReady={vi.fn()} onUnavailable={vi.fn()} />);
    expect(harness.props.frameloop).toBe('demand');
    expect(harness.props.dpr).toEqual([1, 1.5]);
    expect(harness.props.gl.powerPreference).toBe('low-power');
    expect(harness.props.camera).toMatchObject({ position: [8, 7.5, 12], fov: 42 });
    const camera = { lookAt: vi.fn() };
    harness.props.onCreated({ camera });
    expect(camera.lookAt).toHaveBeenCalledWith(0, 1.5, 0);
    view.unmount();
  });

  it('resumes demand animation after a visibility or preference change without replacing the native rig', () => {
    const props = { staged, onReady: vi.fn(), onUnavailable: vi.fn() };
    const view = render(<PedestalScene {...props} motionAllowed={false} />);
    const instance = harness.instances[0];
    act(() => harness.frame({}, 1));
    expect(instance.update).not.toHaveBeenCalled();
    harness.invalidate.mockClear();
    view.rerender(<PedestalScene {...props} motionAllowed />);
    expect(harness.invalidate).toHaveBeenCalled();
    act(() => harness.frame({}, .016));
    expect(instance.update).toHaveBeenCalledWith(.016, { active: true, paused: false, maxDelta: .05 });
    view.rerender(<PedestalScene {...props} motionAllowed={false} />);
    instance.update.mockClear();
    act(() => harness.frame({}, 2));
    expect(instance.update).not.toHaveBeenCalled();
    expect(harness.instances).toHaveLength(1);
    view.unmount();
  });

  it('preserves stable instances and fresh callbacks but reloads changed resolved files or native takes', () => {
    const onReady = vi.fn(), latestReady = vi.fn(), onUnavailable = vi.fn();
    const view = render(<PedestalScene staged={staged} onReady={onReady} onUnavailable={onUnavailable} />);
    view.rerender(<PedestalScene staged={{ ...staged }} onReady={latestReady} onUnavailable={onUnavailable} />);
    expect(harness.instances).toHaveLength(1);
    act(() => harness.instances[0].callbacks.onReady());
    expect(latestReady).toHaveBeenCalledOnce();
    expect(onReady).not.toHaveBeenCalled();
    const changed = { ...staged, resolveUrl: () => '/changed-synthetic.glb' };
    view.rerender(<PedestalScene staged={changed} onReady={latestReady} onUnavailable={onUnavailable} />);
    expect(harness.instances).toHaveLength(2);
    expect(harness.instances[0].dispose).toHaveBeenCalledOnce();
    view.rerender(<PedestalScene staged={changed} eggAssetId="legendary-egg-idle-breath" onReady={latestReady} onUnavailable={onUnavailable} />);
    expect(harness.instances).toHaveLength(3);
    expect(harness.instances[1].dispose).toHaveBeenCalledOnce();
    view.unmount();
    expect(harness.instances[2].dispose).toHaveBeenCalledOnce();
  });

  it('disposes StrictMode abandoned instances independently and cleans the context listener', () => {
    const remove = vi.spyOn(harness.canvas, 'removeEventListener');
    const view = render(<StrictMode><PedestalScene staged={staged} onReady={vi.fn()} onUnavailable={vi.fn()} /></StrictMode>);
    expect(harness.instances).toHaveLength(2);
    expect(harness.instances[0].dispose).toHaveBeenCalledOnce();
    expect(harness.instances[1].dispose).not.toHaveBeenCalled();
    view.unmount();
    expect(harness.instances[1].dispose).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledWith('webglcontextlost', expect.any(Function));
  });

  it('reports failed model loading and context loss to the DOM fallback', () => {
    const unavailable = vi.fn();
    const view = render(<PedestalScene staged={staged} onReady={vi.fn()} onUnavailable={unavailable} />);
    const failure = new Error('Synthetic model failure');
    act(() => harness.instances[0].callbacks.onError(failure));
    expect(unavailable).toHaveBeenCalledWith(failure);
    const event = new Event('webglcontextlost', { cancelable: true });
    act(() => harness.canvas.dispatchEvent(event));
    expect(event.defaultPrevented).toBe(true);
    expect(unavailable).toHaveBeenCalledTimes(2);
    view.unmount();
  });

  it('keeps browser canvas fallback markup inert when the WebGL renderer is healthy', () => {
    const unavailable = vi.fn();
    render(<PedestalScene staged={staged} onReady={vi.fn()} onUnavailable={unavailable} />);
    expect(unavailable).not.toHaveBeenCalled();
    expect(harness.instances).toHaveLength(1);
  });
});
