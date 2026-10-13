import { describe, expect, it } from 'vitest';
import { PerspectiveCamera } from 'three';
import { AVATAR_CAMERA_POSITION, AVATAR_CAMERA_TARGET, createAvatarCameraControls, orbitAvatarCamera } from './avatarCamera';

function fixture() {
  const camera = new PerspectiveCamera(33, 1, 0.1, 100);
  camera.position.fromArray(AVATAR_CAMERA_POSITION);
  const controls = createAvatarCameraControls(camera);
  const canvas = document.createElement('canvas');
  controls.connect(canvas);
  return { camera, controls, canvas };
}

describe('Avatar camera controls', () => {
  it('orbits the centered avatar while preserving distance, then resets the exact front view', () => {
    const { camera, controls } = fixture();
    const front = camera.position.clone();
    const distance = camera.position.distanceTo(controls.target);
    orbitAvatarCamera(controls, 1, 1);
    expect(camera.position.x).toBeLessThan(front.x);
    expect(camera.position.y).toBeGreaterThan(front.y);
    expect(controls.target.toArray()).toEqual(AVATAR_CAMERA_TARGET);
    expect(camera.position.distanceTo(controls.target)).toBeCloseTo(distance);
    controls.reset();
    expect(camera.position.distanceTo(front)).toBeLessThan(1e-10);
    controls.dispose();
  });

  it('keeps repeated vertical rotation within the accepted framing limits', () => {
    const { controls } = fixture();
    for (let step = 0; step < 50; step++) orbitAvatarCamera(controls, 0, 1);
    expect(controls.getPolarAngle()).toBeCloseTo(controls.minPolarAngle);
    for (let step = 0; step < 50; step++) orbitAvatarCamera(controls, 0, -1);
    expect(controls.getPolarAngle()).toBeCloseTo(controls.maxPolarAngle);
    controls.dispose();
  });

  it('leaves mouse-wheel page scrolling available and releases touch handling when disposed', () => {
    const { controls, canvas } = fixture();
    expect(canvas.style.touchAction).toBe('none');
    const wheel = new WheelEvent('wheel', { deltaY: 100, cancelable: true });
    canvas.dispatchEvent(wheel);
    expect(wheel.defaultPrevented).toBe(false);
    expect(controls.enableZoom).toBe(false);
    expect(controls.enablePan).toBe(false);
    expect(controls.enableDamping).toBe(false);
    controls.dispose();
    expect(canvas.style.touchAction).toBe('');
  });
});
