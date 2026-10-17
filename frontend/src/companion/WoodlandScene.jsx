import { useEffect, useMemo } from 'react';
import { useLoader, useThree } from '@react-three/fiber';
import { DataTexture, RGBAFormat } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { prepareWoodland, WOODLAND_BACKGROUND } from './prepareWoodland';

export function WoodlandCamera({ target } = {}) {
  const { camera, size, invalidate } = useThree();
  const [targetX, targetY, targetZ] = target || [0, 0.95, -0.25];
  useEffect(() => {
    // A narrow phone must still contain the supplied Bird's full wingspan.
    const distance = Math.max(0.84, 1.15 / (size.width / Math.max(size.height, 1)));
    camera.position.set(0.8 * distance + targetX, 3.4 * distance + (targetY - 0.95), 8.8 * distance + (targetZ + 0.25));
    camera.lookAt(targetX, targetY, targetZ);
    camera.updateProjectionMatrix();
    invalidate();
  }, [camera, size.width, size.height, invalidate, targetX, targetY, targetZ]);
  return null;
}

function ContactShadow() {
  const texture = useMemo(() => {
    const side = 64;
    const pixels = new Uint8Array(side * side * 4);
    for (let y = 0; y < side; y += 1) {
      for (let x = 0; x < side; x += 1) {
        const radius = Math.hypot((x + 0.5) / side * 2 - 1, (y + 0.5) / side * 2 - 1);
        const offset = (y * side + x) * 4;
        pixels.set([76, 69, 61, Math.round(Math.max(0, 1 - radius) ** 2 * 100)], offset);
      }
    }
    const prepared = new DataTexture(pixels, side, side, RGBAFormat);
    prepared.needsUpdate = true;
    return prepared;
  }, []);
  useEffect(() => () => texture.dispose(), [texture]);
  return <mesh position={[0, 0.015, 0]} rotation={[-Math.PI / 2, 0, 0]}>
    <planeGeometry args={[3.5, 2]} />
    <meshBasicMaterial map={texture} transparent depthWrite={false} />
  </mesh>;
}

export default function WoodlandScene({ appearance }) {
  const gltf = useLoader(GLTFLoader, appearance.url);
  const woodland = useMemo(() => prepareWoodland(gltf.scene), [gltf]);
  useEffect(() => () => woodland.materials.forEach((material) => material.dispose()), [woodland]);
  return <>
    <color attach="background" args={[WOODLAND_BACKGROUND]} />
    <fog attach="fog" args={[WOODLAND_BACKGROUND, 10, 25]} />
    <hemisphereLight args={['#fff4df', '#6e7963', 1.45]} />
    <directionalLight position={[-3, 6, 4]} color="#fff2d8" intensity={2} />
    <directionalLight position={[4, 3, -4]} color="#f1f4e9" intensity={0.65} />
    <primitive object={woodland.scene} scale={appearance.scale} dispose={null} />
    <ContactShadow />
  </>;
}
