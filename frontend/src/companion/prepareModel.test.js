import { describe, expect, it } from 'vitest';
import { Bone, Box3, BoxGeometry, Float32BufferAttribute, Group, MeshBasicMaterial, Skeleton, SkinnedMesh, Uint16BufferAttribute, Vector3 } from 'three';
import { prepareModel } from './prepareModel';

describe('First-frame companion preparation', () => {
  it('frames a scaled, unrendered skeleton correctly and leaves the source reusable', () => {
    const geometry = new BoxGeometry(1, 2, 1);
    const count = geometry.attributes.position.count;
    const weights = Array.from({ length: count }, () => [1, 0, 0, 0]).flat();
    geometry.setAttribute('skinIndex', new Uint16BufferAttribute(new Array(count * 4).fill(0), 4));
    geometry.setAttribute('skinWeight', new Float32BufferAttribute(weights, 4));
    const bone = new Bone();
    const mesh = new SkinnedMesh(geometry, new MeshBasicMaterial());
    mesh.add(bone);
    mesh.bind(new Skeleton([bone]));
    const source = new Group();
    source.add(mesh);
    source.scale.setScalar(3);
    source.position.set(5, 8, -2);
    // No renderer or frame has updated this source's scaled world matrices.
    const prepared = prepareModel(source);
    expect(prepared.scale).toBeCloseTo(1.65 / 6);
    expect(source.scale.x).toBe(3);
    expect(source.position.toArray()).toEqual([5, 8, -2]);
    expect(prepared.scene.children[0].skeleton.bones[0]).not.toBe(bone);
    const presentation = new Group();
    presentation.add(prepared.scene);
    presentation.scale.setScalar(prepared.scale);
    presentation.position.fromArray(prepared.position);
    const bounds = new Box3().setFromObject(presentation, true);
    expect(bounds.getSize(new Vector3()).y).toBeCloseTo(1.65);
    expect(bounds.min.y).toBeCloseTo(0);
  });
});
