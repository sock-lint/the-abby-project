import { Suspense, useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber';
import { AnimationMixer, Group, SRGBColorSpace, TextureLoader } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { prepareModel } from '../companion/prepareModel';
import presentation from '../storybook/presentation.json';
import { createAvatarReactions } from './avatarReactions';
import { AVATAR_CAMERA_POSITION, AVATAR_CAMERA_TARGET, connectAvatarCameraControls, createAvatarCameraControls, orbitAvatarCamera } from './avatarCamera';

function AvatarCamera({ cameraReset, cameraOrbit }) {
  const camera = useThree((state) => state.camera);
  const canvas = useThree((state) => state.gl.domElement);
  const invalidate = useThree((state) => state.invalidate);
  const controls = useMemo(() => createAvatarCameraControls(camera), [camera]);
  const lastOrbit = useRef(0);
  useEffect(() => connectAvatarCameraControls(controls, canvas, invalidate), [canvas, controls, invalidate]);
  useEffect(() => { controls.reset(); invalidate(); }, [cameraReset, controls, invalidate]);
  useEffect(() => {
    if (!cameraOrbit?.id || cameraOrbit.id === lastOrbit.current) return;
    lastOrbit.current = cameraOrbit.id;
    orbitAvatarCamera(controls, cameraOrbit.horizontal, cameraOrbit.vertical);
    invalidate();
  }, [cameraOrbit, controls, invalidate]);
  return null;
}

function Avatar({ appearance, onReady, motionAllowed, interaction }) {
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
  const reactions = useMemo(() => {
    const root = new Group();
    root.rotation.y = appearance.rotationY;
    model.scene.position.fromArray(model.position);
    model.scene.scale.setScalar(model.scale);
    root.add(model.scene);
    return { root, playback: createAvatarReactions(root) };
  }, [model, appearance.rotationY]);
  const lastInteraction = useRef(0);
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
  useEffect(() => {
    if (!motionAllowed) reactions.playback.reset();
    invalidate();
  }, [motionAllowed, reactions, invalidate]);
  useEffect(() => {
    if (!interaction?.id || interaction.id === lastInteraction.current) return;
    lastInteraction.current = interaction.id;
    if (motionAllowed) reactions.playback.play(interaction.action);
    invalidate();
  }, [interaction, motionAllowed, reactions, invalidate]);
  useFrame((_state, delta) => {
    if (!motionAllowed) return;
    if (clip) { mixer.update(Math.min(delta, 0.05)); invalidate(); }
    if (reactions.playback.playing) { reactions.playback.update(delta); invalidate(); }
  });
  return <primitive object={reactions.root} dispose={null} />;
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

export default function AvatarScene({ appearance, onReady, onUnavailable, interaction, cameraReset = 0, cameraOrbit, motionAllowed = true }) {
  return <Canvas frameloop="demand" dpr={[1, 1.5]} camera={{ position: AVATAR_CAMERA_POSITION, fov: 33 }} gl={{ antialias: true, alpha: false, powerPreference: 'low-power' }}
    onCreated={({ camera }) => { camera.lookAt(...AVATAR_CAMERA_TARGET); }} fallback="Your browser could not display the character.">
    <color attach="background" args={[presentation.palette.sky]} />
    <ambientLight intensity={1.8} />
    <directionalLight position={[3, 6, 4]} intensity={2.2} />
    <ContextGuard onUnavailable={onUnavailable} />
    <AvatarCamera cameraReset={cameraReset} cameraOrbit={cameraOrbit} />
    <Suspense fallback={null}><Avatar appearance={appearance} onReady={onReady} motionAllowed={motionAllowed} interaction={interaction} /></Suspense>
  </Canvas>;
}
