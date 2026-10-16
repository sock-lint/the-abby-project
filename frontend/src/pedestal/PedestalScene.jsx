import { useEffect, useEffectEvent, useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Group } from 'three';
import { createPedestalPlayback } from './pedestalPlayback';
import { pedestalPlaybackIdentity } from './pedestal.constants';

function Models({ staged, eggAssetId, motionAllowed, onReady, onUnavailable }) {
  const root = useMemo(() => new Group(), []);
  const playback = useRef(null);
  const invalidate = useThree((state) => state.invalidate);
  const notifyReady = useEffectEvent(() => onReady());
  const notifyUnavailable = useEffectEvent((error) => onUnavailable(error));
  const createPlayback = useEffectEvent(() => createPedestalPlayback(staged, {
    eggAssetId, onReady: () => notifyReady(), onError: (error) => notifyUnavailable(error), invalidate,
  }));
  const identity = pedestalPlaybackIdentity(staged, eggAssetId);
  useEffect(() => {
    const instance = createPlayback();
    playback.current = instance;
    root.add(instance.root);
    // Effect ownership disposes abandoned StrictMode instances and in-flight
    // requests without disposing the rig used by the committed render.
    return () => {
      playback.current = null;
      instance.dispose();
      root.remove(instance.root);
    };
  }, [identity, root]);
  useEffect(() => { invalidate(); }, [motionAllowed, invalidate]);
  useFrame((_state, delta) => {
    if (!motionAllowed) return;
    playback.current?.update(delta, { active: true, paused: false, maxDelta: 0.05 });
    invalidate();
  });
  return <primitive object={root} dispose={null} />;
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

export default function PedestalScene({ staged, eggAssetId = 'normal-egg', motionAllowed = true, onReady, onUnavailable }) {
  // The pedestal is almost ten metres wide in its authored units. Frame that
  // native composition with the camera rather than normalizing every model.
  return <Canvas frameloop="demand" dpr={[1, 1.5]} camera={{ position: [8, 7.5, 12], fov: 42, near: 0.1, far: 80 }}
    gl={{ antialias: true, alpha: true, powerPreference: 'low-power' }}
    onCreated={({ camera }) => camera.lookAt(0, 1.5, 0)}
    fallback={<span>3D display is unavailable on this device.</span>}>
    <ambientLight intensity={2} />
    <directionalLight position={[4, 8, 6]} intensity={2.5} />
    <ContextGuard onUnavailable={onUnavailable} />
    <Models staged={staged} eggAssetId={eggAssetId} motionAllowed={motionAllowed} onReady={onReady} onUnavailable={onUnavailable} />
  </Canvas>;
}
