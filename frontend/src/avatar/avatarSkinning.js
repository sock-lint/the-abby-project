import { Matrix4, ShaderChunk, Vector4 } from 'three';

const EPSILON = 1e-6;

function extraAttributes(mesh) {
  const attributes = mesh.geometry?.attributes || {};
  const extra = Object.keys(attributes).filter((key) => /^(joints|weights)_\d+$/.test(key));
  if (!extra.length) return null;
  if (!mesh.isSkinnedMesh || extra.some((key) => !['joints_1', 'weights_1'].includes(key))
    || !attributes.joints_1 || !attributes.weights_1) throw new Error('Avatar has unsupported additional skin influences.');
  const pairs = [[attributes.skinIndex, attributes.skinWeight], [attributes.joints_1, attributes.weights_1]];
  for (const [indices, weights] of pairs) {
    if (!indices || !weights || indices.itemSize !== 4 || weights.itemSize !== 4
      || indices.count !== attributes.position.count || weights.count !== attributes.position.count) {
      throw new Error('Avatar skin influence attributes do not match its vertices.');
    }
  }
  for (let vertex = 0; vertex < attributes.position.count; vertex += 1) {
    for (const [indices, weights] of pairs) {
      for (let component = 0; component < 4; component += 1) {
        const joint = indices.getComponent(vertex, component);
        const weight = weights.getComponent(vertex, component);
        if (!Number.isInteger(joint) || joint < 0 || joint >= mesh.skeleton.bones.length
          || !Number.isFinite(weight) || weight < 0 || weight > 1) throw new Error('Avatar skin influences are invalid.');
      }
    }
    const total = (attribute) => [0, 1, 2, 3].reduce((sum, component) => sum + attribute.getComponent(vertex, component), 0);
    // GLTFLoader normalizes WEIGHTS_0 independently. The reviewed GLB stores
    // normalized totals across both sets, so retain _1 and restore _0's share.
    if (Math.abs(total(attributes.skinWeight) - 1) > EPSILON || total(attributes.weights_1) > 1 + EPSILON) {
      throw new Error('Avatar additional skin weights cannot restore the reviewed total.');
    }
  }
  return pairs;
}

export function validateAvatarSkinning(scene) {
  scene.traverse((node) => { if (node.geometry) extraAttributes(node); });
}

function replaceRequired(source, marker, replacement) {
  if (!source.includes(marker)) throw new Error('Avatar skin shader is incompatible with this Three version.');
  return source.replace(marker, replacement);
}

/** Add the second supplied influence set to both position and normal blends. */
export function configureAvatarSkinMaterial(material) {
  const originalCompile = material.onBeforeCompile;
  const originalKey = material.customProgramCacheKey();
  material.customProgramCacheKey = () => `${originalKey}:abby-eight-influences-v1`;
  material.onBeforeCompile = function (shader, renderer) {
    originalCompile.call(this, shader, renderer);
    const extraMatrices = ['X', 'Y', 'Z', 'W'].map((axis, index) => `mat4 boneMatExtra${axis} = getBoneMatrix( skinIndexExtra.${'xyzw'[index]} );`).join('\n');
    const positionBlend = ['X', 'Y', 'Z', 'W'].map((axis, index) => `skinned += boneMatExtra${axis} * skinVertex * skinWeightExtra.${'xyzw'[index]};`).join('\n');
    const normalBlend = ['X', 'Y', 'Z', 'W'].map((axis, index) => `skinMatrix += skinWeightExtra.${'xyzw'[index]} * boneMatExtra${axis};`).join('\n');
    shader.vertexShader = replaceRequired(shader.vertexShader, '#include <skinning_pars_vertex>', `${ShaderChunk.skinning_pars_vertex}\n#ifdef USE_SKINNING\nattribute vec4 skinIndexExtra;\nattribute vec4 skinWeightExtra;\n#endif`);
    shader.vertexShader = replaceRequired(shader.vertexShader, '#include <skinbase_vertex>', replaceRequired(ShaderChunk.skinbase_vertex, '#endif', `${extraMatrices}\n#endif`));
    shader.vertexShader = replaceRequired(shader.vertexShader, '#include <skinning_vertex>', replaceRequired(ShaderChunk.skinning_vertex, 'transformed =', `${positionBlend}\ntransformed =`));
    shader.vertexShader = replaceRequired(shader.vertexShader, '#include <skinnormal_vertex>', replaceRequired(ShaderChunk.skinnormal_vertex, 'skinMatrix = bindMatrixInverse', `${normalBlend}\nskinMatrix = bindMatrixInverse`));
  };
}

/** Prepare a private eight-influence geometry and matching CPU bounds/raycast. */
export function prepareAvatarSkinning(mesh) {
  if (!extraAttributes(mesh)) return null;
  const geometry = mesh.geometry.clone();
  const { skinWeight, joints_1: extraIndices, weights_1: extraWeights } = geometry.attributes;
  for (let vertex = 0; vertex < skinWeight.count; vertex += 1) {
    let primary = 0;
    let additional = 0;
    for (let component = 0; component < 4; component += 1) {
      primary += skinWeight.getComponent(vertex, component);
      additional += extraWeights.getComponent(vertex, component);
    }
    for (let component = 0; component < 4; component += 1) {
      skinWeight.setComponent(vertex, component, skinWeight.getComponent(vertex, component) / primary * Math.max(0, 1 - additional));
    }
  }
  geometry.setAttribute('skinIndexExtra', extraIndices);
  geometry.setAttribute('skinWeightExtra', extraWeights);
  mesh.geometry = geometry;
  mesh.boundingBox = null;
  mesh.boundingSphere = null;
  const base = new Vector4();
  const transformed = new Vector4();
  const boneMatrix = new Matrix4();
  mesh.applyBoneTransform = function (vertex, target) {
    const direction = target.isVector4;
    base.set(target.x, target.y, target.z, direction ? target.w : 1).applyMatrix4(this.bindMatrix);
    if (direction) target.set(0, 0, 0, 0);
    else target.set(0, 0, 0);
    for (const [indices, weights] of [[geometry.attributes.skinIndex, skinWeight], [extraIndices, extraWeights]]) {
      for (let component = 0; component < 4; component += 1) {
        const weight = weights.getComponent(vertex, component);
        if (!weight) continue;
        const joint = indices.getComponent(vertex, component);
        boneMatrix.multiplyMatrices(this.skeleton.bones[joint].matrixWorld, this.skeleton.boneInverses[joint]);
        target.addScaledVector(transformed.copy(base).applyMatrix4(boneMatrix), weight);
      }
    }
    if (direction) target.w = base.w;
    return target.applyMatrix4(this.bindMatrixInverse);
  };
  return geometry;
}
