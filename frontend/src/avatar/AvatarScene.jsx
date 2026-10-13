import { Suspense, useEffect, useMemo, useState } from 'react';
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber';
import { AnimationMixer, SRGBColorSpace, TextureLoader } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { prepareModel } from '../companion/prepareModel';
import presentation from '../storybook/presentation.json';

function useMotionAllowed() {
  const [allowed, setAllowed] = useState(() => !document.hidden && !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setAllowed(!document.hidden && !media.matches);
    document.addEventListener('visibilitychange', update);
    media.addEventListener('change', update);
    return () => { document.removeEventListener('visibilitychange', update); media.removeEventListener('change', update); };
  }, []);
  return allowed;
}

function Avatar({ appearance, onReady, motionAllowed }) {
  const gltf = useLoader(GLTFLoader, appearance.url);
  const maps = useLoader(TextureLoader, Object.values(appearance.textures));
  const invalidate = useThree((state) => state.invalidate);
  const model = useMemo(() => {
    const prepared = prepareModel(gltf.scene);
    const localTextures = maps.map((texture) => {
      const local = texture.clone();
      local.flipY = false;
      local.colorSpace = SRGBColorSpace;
      local.needsUpdate = true;
      return local;
    });
    const [body, hair, face] = localTextures;
    const partNames = appearance.parts;
    const selectedHair = partNames.hair[appearance.hairStyle];
    const hairNames = Object.values(partNames.hair);
    const localMaterials = [];
    const localSkeletons = new Set();
    const required = [partNames.body, partNames.head, partNames.face, ...hairNames];
    for (const name of required) if (!prepared.scene.getObjectByName(name)) throw new Error(`Avatar asset is missing ${name}.`);
    prepared.scene.traverse((node) => {
      if (node.skeleton) localSkeletons.add(node.skeleton);
      if (hairNames.includes(node.name)) node.visible = node.name === selectedHair;
      const texture = node.name === partNames.body || node.name === partNames.head ? body
        : node.name === partNames.face ? face : hairNames.includes(node.name) ? hair : null;
      if (!texture || !node.material) return;
      const replace = (material) => { const local = material.clone(); local.map = texture; local.needsUpdate = true; localMaterials.push(local); return local; };
      node.material = Array.isArray(node.material) ? node.material.map(replace) : replace(node.material);
    });
    return { ...prepared, localMaterials, localTextures, localSkeletons };
  }, [gltf, maps, appearance]);
  const mixer = useMemo(() => new AnimationMixer(model.scene), [model]);
  const clip = gltf.animations.find((entry) => entry.name === appearance.idleClip);
  if (appearance.idleClip && !clip) throw new Error('Avatar asset is missing its reviewed idle clip.');
  useEffect(() => {
    if (clip) mixer.clipAction(clip).play();
    return () => { mixer.stopAllAction(); mixer.uncacheRoot(model.scene); };
  }, [clip, mixer, model]);
  useEffect(() => {
    onReady();
    invalidate();
    return () => {
      model.localMaterials.forEach((material) => material.dispose());
      model.localTextures.forEach((texture) => texture.dispose());
      model.localSkeletons.forEach((skeleton) => skeleton.dispose());
    };
  }, [model, onReady, invalidate]);
  useEffect(() => { invalidate(); }, [motionAllowed, invalidate]);
  useFrame((_state, delta) => {
    if (motionAllowed && clip) { mixer.update(Math.min(delta, 0.05)); invalidate(); }
  });
  return <group rotation={[0, appearance.rotationY, 0]}><primitive object={model.scene} position={model.position} scale={model.scale} dispose={null} /></group>;
}

function ContextGuard({ onUnavailable }) {
  const canvas = useThree((state) => state.gl.domElement);
  useEffect(() => {
    const lost = (event) => { event.preventDefault(); onUnavailable(); };
    canvas.addEventListener('webglcontextlost', lost);
    return () => canvas.removeEventListener('webglcontextlost', lost);
  }, [canvas, onUnavailable]);
  return null;
}

export default function AvatarScene({ appearance, onReady, onUnavailable }) {
  const motionAllowed = useMotionAllowed();
  return <Canvas frameloop="demand" dpr={[1, 1.5]} camera={{ position: [0, 1.05, 3.7], fov: 33 }} gl={{ antialias: true, alpha: false, powerPreference: 'low-power' }}
    onCreated={({ camera }) => { camera.lookAt(0, 0.9, 0); }} fallback="Your browser could not display the character.">
    <color attach="background" args={[presentation.palette.sky]} />
    <ambientLight intensity={1.8} />
    <directionalLight position={[3, 6, 4]} intensity={2.2} />
    <ContextGuard onUnavailable={onUnavailable} />
    <Suspense fallback={null}><Avatar appearance={appearance} onReady={onReady} motionAllowed={motionAllowed} /></Suspense>
  </Canvas>;
}
