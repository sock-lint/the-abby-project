import { Group } from 'three';

export const WOODLAND_BACKGROUND = '#e8ebdf';
export const WOODLAND_CAMERA = { position: [0.8, 3.4, 8.8], fov: 34 };

// These are arrangements of the five meshes in the owned woodland export.
// Scenery is shared presentation, never furnishing inventory or an unlock.
const TREES = [
  [-5.5, -2.8, 2.7, 0.3], [-4.4, -6.2, 2.1, -0.4],
  [-6.6, -11.2, 1.7, 0.6], [5.6, -2.5, 2.6, -0.3],
  [4.3, -7.3, 2.1, 0.5], [7.3, -11.5, 2.8, -0.6],
  [-2.1, -14.6, 1.15, 0.2], [1.6, -17.8, 1.35, 0.5],
  [-7.8, -17.2, 2, -0.2],
];

function namedNode(scene, name) {
  // GLTFLoader sanitizes spaces in source node names.
  const normalized = name.replaceAll(' ', '_');
  let found;
  scene.traverse((node) => {
    if (!found && node.name.replaceAll(' ', '_') === normalized) found = node;
  });
  if (!found) throw new Error(`The owned woodland is missing ${name}.`);
  return found;
}

export function prepareWoodland(source) {
  const scene = new Group();
  const materials = new Map();
  const ground = namedNode(source, 'Ground');
  const tree = namedNode(source, 'Tree left');
  const rock = namedNode(source, 'Rock left');
  const mushroom = namedNode(source, 'Mushroom');
  const pillar = namedNode(source, 'Ruin');

  function add(template, name, position, scale, rotation, palette) {
    const object = template.clone(true);
    object.name = name;
    object.position.set(...position);
    object.scale.multiplyScalar(scale);
    object.rotation.y += rotation;
    object.traverse((node) => {
      if (!node.isMesh) return;
      const tint = (material) => {
        const key = `${palette}:${material.uuid}`;
        if (!materials.has(key)) {
          const prepared = material.clone();
          if (palette === 'foliage') {
            const leaves = /Leaves/.test(material.name);
            prepared.color.set(leaves ? '#ffffff' : '#d4c6af');
            if (leaves) {
              prepared.onBeforeCompile = (shader) => {
                shader.fragmentShader = shader.fragmentShader.replace(
                  '#include <map_fragment>',
                  `#include <map_fragment>
                   float leafLuminance = dot(diffuseColor.rgb, vec3(0.2126, 0.7152, 0.0722));
                   diffuseColor.rgb = mix(vec3(leafLuminance), vec3(0.32, 0.43, 0.29), 0.62);`,
                );
              };
              prepared.customProgramCacheKey = () => 'woodland-soft-leaves-v2';
            }
          } else if (palette === 'ground') {
            prepared.color.set('#ffffff');
            // The atlas's bright green grass otherwise overwhelms a small
            // canvas. Reduce its saturation without changing private pixels.
            prepared.onBeforeCompile = (shader) => {
              shader.fragmentShader = shader.fragmentShader.replace(
                '#include <map_fragment>',
                `#include <map_fragment>
                 float grassLuminance = dot(diffuseColor.rgb, vec3(0.2126, 0.7152, 0.0722));
                 diffuseColor.rgb = mix(vec3(grassLuminance), vec3(0.58, 0.65, 0.43), 0.7);`,
              );
            };
            prepared.customProgramCacheKey = () => 'woodland-warm-grass-v2';
          } else {
            prepared.color.set('#d5ceba');
          }
          materials.set(key, prepared);
        }
        return materials.get(key);
      };
      node.material = Array.isArray(node.material) ? node.material.map(tint) : tint(node.material);
    });
    scene.add(object);
    return object;
  }

  // Keep the source island's rim beyond the camera. Fog, rather than a hard
  // curved boundary, lets the clearing recede into the distant grove.
  const floor = add(ground, 'Clearing floor', [0, -0.012, -10], 1, 0, 'ground');
  floor.scale.x *= 10;
  floor.scale.z *= 12;
  TREES.forEach(([x, z, size, turn], index) => {
    add(tree, `Grove tree ${index + 1}`, [x, tree.position.y * size, z], size, turn, 'foliage');
  });
  add(rock, 'Near left rock', [-2.9, 0, 0.6], 0.7, 0.4, 'stone');
  add(rock, 'Right grove rock', [3.2, 0, -2.2], 0.6, -0.5, 'stone');
  add(rock, 'Far left rock', [-3.9, 0, -3.8], 0.45, 1.2, 'stone');
  add(mushroom, 'Near mushroom', [-2.4, 0, 0.9], 0.75, 0.2, 'detail');
  add(mushroom, 'Small mushroom', [-2.8, 0, 0.65], 0.5, -0.4, 'detail');
  add(pillar, 'Grove ruin', [3.1, 0, -3.5], 0.95, -0.3, 'stone');
  return { scene, materials: [...materials.values()] };
}
