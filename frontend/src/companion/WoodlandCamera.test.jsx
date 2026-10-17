import { render } from '@testing-library/react';
import { PerspectiveCamera, Vector3 } from 'three';
import { beforeEach, expect, it, vi } from 'vitest';
import { WoodlandCamera } from './WoodlandScene';
import { rosterFraming } from './rosterFraming';

const state = vi.hoisted(() => ({ camera: null, size: { width: 358, height: 330 }, invalidate: vi.fn() }));
vi.mock('@react-three/fiber', () => ({ useThree: () => state, useLoader: vi.fn() }));
beforeEach(() => { state.camera = new PerspectiveCamera(34, state.size.width / state.size.height, 0.1, 100); });

it('frames an elevated native flying idle through camera focus without moving its geometry', () => {
  const bounds = { min: [-0.6, 2.4, -0.3], max: [0.6, 3.8, 0.3] };
  const framing = rosterFraming(bounds);
  const nativeIdleCenter = new Vector3().fromArray(framing.center);
  render(<WoodlandCamera target={framing.center} />);
  state.camera.updateMatrixWorld();
  const projected = nativeIdleCenter.clone().project(state.camera);
  expect(projected.y).toBeCloseTo(0, 8);
  expect(projected.x).toBeCloseTo(0, 8);
  for (const corner of [new Vector3().fromArray(bounds.min), new Vector3().fromArray(bounds.max)]) {
    corner.multiplyScalar(framing.scale);
    const visible = corner.project(state.camera);
    expect(Math.abs(visible.x)).toBeLessThan(1);
    expect(Math.abs(visible.y)).toBeLessThan(1);
  }
});

it('retains the existing Bird camera when no roster focus is supplied', () => {
  render(<WoodlandCamera />);
  const distance = 1.15 / (358 / 330);
  expect(state.camera.position.toArray()).toEqual([0.8 * distance, 3.4 * distance, 8.8 * distance]);
});
