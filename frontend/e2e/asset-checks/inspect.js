import { AnimationMixer, Box3, DoubleSide, Vector3 } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { clone } from 'three/addons/utils/SkeletonUtils.js';
import { prepareModel } from '../../src/companion/prepareModel';

function requireValue(value) { if (!value) throw new Error('ASSET_INSPECTION_FAILED'); }
function points(scene) {
  scene.updateMatrixWorld(true);
  scene.traverse((node) => node.skeleton?.update());
  const result = [];
  scene.traverse((node) => {
    if (!node.isMesh) return;
    requireValue(node.geometry.attributes.position.count < 500000);
    for (let index = 0; index < node.geometry.attributes.position.count; index += 1) {
      const point = node.getVertexPosition(index, new Vector3()).applyMatrix4(node.matrixWorld);
      requireValue(point.toArray().every(Number.isFinite));
      result.push(point);
    }
  });
  requireValue(result.length > 0);
  return result;
}
export async function inspectAssets(manifest) {
  const loader = new GLTFLoader();
  let skinCount = 0;
  for (const key of ['chick', 'bird']) {
    const model = manifest.models[key];
    requireValue(model.idle_clip && model.interaction_clips?.play && model.interaction_clips?.left && model.interaction_clips?.right);
    const takes = [{ file: model.file, clip: model.idle_clip }, ...Object.values(model.interaction_clips)];
    for (let index = 0; index < takes.length; index += 1) {
      const take = takes[index];
      const gltf = await loader.loadAsync('/src/companion/licensed/' + take.file);
      const scene = clone(gltf.scene);
      const clip = gltf.animations.find((entry) => entry.name === take.clip);
      requireValue(clip && clip.duration > 0);
      scene.traverse((node) => {
        if (node.isSkinnedMesh) { skinCount += 1; requireValue(node.skeleton.bones.length > 0); }
        if (node.isMesh) requireValue(node.geometry.attributes.uv && node.material);
      });
      const mixer = new AnimationMixer(scene);
      mixer.clipAction(clip).play();
      const snapshots = [0, clip.duration * 0.5, clip.duration * 0.99].map((time) => {
        mixer.setTime(time);
        return points(scene);
      });
      requireValue(snapshots[0].length === snapshots[1].length
        && snapshots[0].some((point, vertex) => point.distanceTo(snapshots[1][vertex]) > 0.00001));
      const bounds = new Box3().setFromPoints(snapshots.flat());
      const size = bounds.getSize(new Vector3());
      requireValue(size.toArray().every((value) => Number.isFinite(value) && value < 20) && size.y > 0.01);
      if (index === 0) {
        mixer.setTime(0);
        const prepared = prepareModel(scene);
        prepared.scene.scale.setScalar(prepared.scale);
        prepared.scene.position.fromArray(prepared.position);
        const resting = new Box3().setFromPoints(points(prepared.scene));
        requireValue(Math.abs(resting.min.y) < 0.05 && resting.max.y > 1 && resting.max.y < 3);
      }
      mixer.stopAllAction();
      mixer.uncacheRoot(scene);
    }
  }
  requireValue(skinCount >= 8);
  const forest = await loader.loadAsync('/src/companion/licensed/woodland.glb');
  requireValue(forest.animations.length === 0);
  let textured = 0, foliage = 0, stems = 0;
  forest.scene.traverse((node) => {
    if (!node.isMesh) return;
    points(node);
    requireValue(node.geometry.attributes.uv);
    if (/Tree_02|Tree 02/.test(node.name) && !/Leaves/.test(node.name)) stems += 1;
    for (const material of Array.isArray(node.material) ? node.material : [node.material]) {
      requireValue(material && material.map?.image && material.map.image.width > 0 && material.map.image.height > 0);
      textured += 1;
      if (/Leaves/.test(material.name)) {
        requireValue(material.side === DoubleSide && material.alphaTest > 0);
        foliage += 1;
      }
    }
  });
  requireValue(textured > 0 && foliage > 0 && stems === 3);
  return { structure: true, materials: true, animation: true, grounding: true };
}
