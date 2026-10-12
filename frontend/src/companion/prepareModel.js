import { Box3, Vector3 } from 'three';
import { clone } from 'three/addons/utils/SkeletonUtils.js';

export function prepareModel(source) {
  const scene = clone(source);
  // A newly cloned skeleton has not been rendered yet. Measuring it before
  // updating bone matrices can make an ordinary model appear millimeters
  // tall and then inflate it far beyond the camera when its first frame runs.
  scene.updateMatrixWorld(true);
  scene.traverse((node) => { if (node.skeleton) node.skeleton.update(); });
  const bounds = new Box3().setFromObject(scene, true);
  const size = bounds.getSize(new Vector3());
  const center = bounds.getCenter(new Vector3());
  const scale = 1.65 / Math.max(size.y, 0.001);
  return { scene, scale, position: [-center.x * scale, -bounds.min.y * scale, -center.z * scale] };
}
