import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export const AVATAR_CAMERA_POSITION = [0, 1.05, 3.7];
export const AVATAR_CAMERA_TARGET = [0, 0.9, 0];
const KEYBOARD_ORBIT_STEP = Math.PI / 15;

export function createAvatarCameraControls(camera) {
  const controls = new OrbitControls(camera);
  controls.target.fromArray(AVATAR_CAMERA_TARGET);
  controls.enablePan = false;
  controls.enableZoom = false;
  controls.enableDamping = false;
  controls.minPolarAngle = Math.PI / 3;
  controls.maxPolarAngle = Math.PI * 0.6;
  controls.rotateSpeed = 0.65;
  controls.update();
  controls.saveState();
  return controls;
}

export function orbitAvatarCamera(controls, horizontal = 0, vertical = 0) {
  controls.rotateLeft(horizontal * KEYBOARD_ORBIT_STEP);
  controls.rotateUp(vertical * KEYBOARD_ORBIT_STEP);
}

export function connectAvatarCameraControls(controls, canvas, invalidate) {
  const touchAction = canvas.style.touchAction;
  const cursor = canvas.style.cursor;
  controls.connect(canvas);
  // Single-finger drags orbit in both axes; native pinch zoom stays available.
  canvas.style.touchAction = 'pinch-zoom';
  controls.cursorStyle = 'grab';
  controls.addEventListener('change', invalidate);
  return () => {
    controls.removeEventListener('change', invalidate);
    controls.dispose();
    canvas.style.touchAction = touchAction;
    canvas.style.cursor = cursor;
  };
}
