import { describe, expect, it } from 'vitest';
import { BoxGeometry, Group, Mesh, MeshStandardMaterial } from 'three';
import { prepareWoodland } from './prepareWoodland';

function ownedSubset() {
  const source = new Group();
  const material = new MeshStandardMaterial({ color: '#00b4c8' });
  material.name = 'Tree 02 Leaves Runtime';
  ['Ground', 'Tree_left', 'Rock_left', 'Mushroom', 'Ruin'].forEach((name) => {
    const node = new Group();
    node.name = name;
    node.add(new Mesh(new BoxGeometry(), material));
    source.add(node);
  });
  return { source, material };
}

describe('owned woodland composition', () => {
  it('reuses owned geometry without recoloring cached materials or changing source transforms', () => {
    const { source, material } = ownedSubset();
    const originalColor = material.color.getHex();
    const woodland = prepareWoodland(source);
    const firstTree = woodland.scene.getObjectByName('Grove tree 1');
    expect(firstTree.children[0].geometry).toBe(source.getObjectByName('Tree_left').children[0].geometry);
    expect(firstTree.children[0].material).not.toBe(material);
    expect(material.color.getHex()).toBe(originalColor);
    expect(source.getObjectByName('Tree_left').position.toArray()).toEqual([0, 0, 0]);
    expect(woodland.scene.children.filter((node) => node.name.startsWith('Grove tree'))).toHaveLength(9);
  });

  it('isolates repeated mounted clearings while sharing their loaded geometry', () => {
    const { source } = ownedSubset();
    const first = prepareWoodland(source);
    const second = prepareWoodland(source);
    first.scene.position.x = 10;
    expect(second.scene.position.x).toBe(0);
    expect(first.materials[0]).not.toBe(second.materials[0]);
  });

  it('requires the actual owned export rather than substituting new scenery', () => {
    expect(() => prepareWoodland(new Group())).toThrow('missing Ground');
  });
});
