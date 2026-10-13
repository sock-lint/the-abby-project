import { describe, expect, it, vi } from 'vitest';
import { Bone, BufferGeometry, Float32BufferAttribute, Group, Matrix4, MeshStandardMaterial, ShaderLib, Skeleton, SkinnedMesh, Uint16BufferAttribute, Vector3, Vector4 } from 'three';
import { configureAvatarSkinMaterial, prepareAvatarSkinning, validateAvatarSkinning } from './avatarSkinning';

const originalWeights = [0.1, 0.2, 0.15, 0.25, 0.3];

function suppliedFiveWeights() {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute([1, 2, 3], 3));
  geometry.setAttribute('normal', new Float32BufferAttribute([0, 1, 0], 3));
  geometry.setAttribute('skinIndex', new Uint16BufferAttribute([0, 1, 2, 3], 4));
  geometry.setAttribute('skinWeight', new Float32BufferAttribute(originalWeights.slice(0, 4), 4));
  geometry.setAttribute('joints_1', new Uint16BufferAttribute([4, 0, 0, 0], 4));
  geometry.setAttribute('weights_1', new Float32BufferAttribute([originalWeights[4], 0, 0, 0], 4));
  const mesh = new SkinnedMesh(geometry, new MeshStandardMaterial());
  const bones = Array.from({ length: 5 }, () => new Bone());
  mesh.add(...bones);
  mesh.bind(new Skeleton(bones));
  // Match the installed GLTFLoader's normalization of its first set only.
  mesh.normalizeSkinWeights();
  return mesh;
}

function animate(mesh) {
  const bones = mesh.skeleton.bones;
  bones[0].position.x = 0.1;
  bones[1].position.y = 0.2;
  bones[2].rotation.x = 0.5;
  bones[3].rotation.y = 0.6;
  bones[4].rotation.z = 0.7;
  bones[4].position.x = 1;
  mesh.updateMatrixWorld(true);
  mesh.skeleton.update();
}

function independentBlend(mesh, vector) {
  const bound = vector.clone().applyMatrix4(mesh.bindMatrix);
  const result = new Vector4(0, 0, 0, 0);
  mesh.skeleton.bones.forEach((bone, index) => {
    const matrix = new Matrix4().multiplyMatrices(bone.matrixWorld, mesh.skeleton.boneInverses[index]);
    result.addScaledVector(bound.clone().applyMatrix4(matrix), originalWeights[index]);
  });
  return result.applyMatrix4(mesh.bindMatrixInverse);
}

describe('owned Archer extra skin influences', () => {
  it('restores all five original weights and deforms points and normals with an independent full matrix blend', () => {
    const mesh = suppliedFiveWeights();
    animate(mesh);
    const point = new Vector4(1, 2, 3, 1);
    const expected = independentBlend(mesh, point);
    const truncated = mesh.applyBoneTransform(0, point.clone());
    expect(truncated.sub(expected).length()).toBeGreaterThan(0.1);
    const cachedGeometry = mesh.geometry;
    const cachedWeights = [...cachedGeometry.attributes.skinWeight.array];
    const geometry = prepareAvatarSkinning(mesh);
    expect(geometry).not.toBe(cachedGeometry);
    expect([...cachedGeometry.attributes.skinWeight.array]).toEqual(cachedWeights);
    for (let component = 0; component < 4; component += 1) {
      expect(geometry.attributes.skinWeight.getComponent(0, component)).toBeCloseTo(originalWeights[component], 6);
    }
    expect(mesh.applyBoneTransform(0, point.clone()).sub(expected).length()).toBeLessThan(1e-6);
    const normal = new Vector4(0, 1, 0, 0);
    expect(mesh.applyBoneTransform(0, normal.clone()).sub(independentBlend(mesh, normal)).length()).toBeLessThan(1e-6);
    mesh.computeBoundingBox();
    expect(mesh.boundingBox.min.distanceTo(new Vector3(expected.x, expected.y, expected.z))).toBeLessThan(1e-6);
    expect(mesh.boundingBox.max.distanceTo(new Vector3(expected.x, expected.y, expected.z))).toBeLessThan(1e-6);
  });

  it('extends the installed standard shader position and normal blends and isolates its program cache', () => {
    const material = new MeshStandardMaterial();
    const originalKey = material.customProgramCacheKey();
    configureAvatarSkinMaterial(material);
    const shader = { vertexShader: ShaderLib.standard.vertexShader };
    material.onBeforeCompile(shader);
    expect(material.customProgramCacheKey()).not.toBe(originalKey);
    expect(shader.vertexShader).toContain('attribute vec4 skinIndexExtra;');
    expect(shader.vertexShader).toContain('attribute vec4 skinWeightExtra;');
    for (const [index, axis] of ['X', 'Y', 'Z', 'W'].entries()) {
      expect(shader.vertexShader).toContain(`skinned += boneMatExtra${axis} * skinVertex * skinWeightExtra.${'xyzw'[index]};`);
      expect(shader.vertexShader).toContain(`skinMatrix += skinWeightExtra.${'xyzw'[index]} * boneMatExtra${axis};`);
    }
    expect(() => material.onBeforeCompile({ vertexShader: 'unsupported shader' })).toThrow('incompatible');
  });

  it('leaves ordinary four-influence models shared and disposes only cloned geometry', () => {
    const mesh = suppliedFiveWeights();
    const source = mesh.geometry;
    const sourceDisposed = vi.spyOn(source, 'dispose');
    const privateGeometry = prepareAvatarSkinning(mesh);
    const privateDisposed = vi.spyOn(privateGeometry, 'dispose');
    privateGeometry.dispose();
    expect(privateDisposed).toHaveBeenCalledOnce();
    expect(sourceDisposed).not.toHaveBeenCalled();
    mesh.geometry = source;
    source.deleteAttribute('joints_1');
    source.deleteAttribute('weights_1');
    expect(prepareAvatarSkinning(mesh)).toBeNull();
    expect(mesh.geometry).toBe(source);
  });

  it.each(['partial', 'third-set', 'negative', 'too-much', 'invalid-joint', 'wrong-count'])('rejects %s extra influence data before cloning', (failure) => {
    const mesh = suppliedFiveWeights();
    const attributes = mesh.geometry.attributes;
    if (failure === 'partial') mesh.geometry.deleteAttribute('joints_1');
    if (failure === 'third-set') mesh.geometry.setAttribute('weights_2', attributes.weights_1.clone());
    if (failure === 'negative') attributes.weights_1.setX(0, -0.1);
    if (failure === 'too-much') attributes.weights_1.setXYZW(0, 0.6, 0.6, 0, 0);
    if (failure === 'invalid-joint') attributes.joints_1.setX(0, 5);
    if (failure === 'wrong-count') mesh.geometry.setAttribute('weights_1', new Float32BufferAttribute([], 4));
    const cloned = vi.spyOn(mesh.geometry, 'clone');
    const scene = new Group();
    scene.add(mesh);
    expect(() => validateAvatarSkinning(scene)).toThrow(/skin/);
    expect(() => prepareAvatarSkinning(mesh)).toThrow(/skin/);
    expect(cloned).not.toHaveBeenCalled();
  });
});
