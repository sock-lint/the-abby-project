import { Component, lazy, Suspense, useCallback, useId, useMemo, useRef, useState } from 'react';
import { UserRound } from 'lucide-react';
import Button from '../Button';
import { resolveAvatarAppearance } from '../../avatar/appearance';
import useSceneMotionAllowed from '../../companion/useSceneMotionAllowed';

const REACTIONS = ['hop', 'twirl', 'bow'];
const TAP_SLOP = 8;

class AvatarBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) { this.props.onFailure(error); }
  render() { return this.state.failed ? null : this.props.children; }
}

export default function AvatarPreview({ preferences }) {
  const appearance = useMemo(() => resolveAvatarAppearance(preferences), [preferences]);
  const identity = [appearance?.url, appearance?.hairStyle, ...Object.values(appearance?.textures || {})].join(':');
  return <Preview key={identity} appearance={appearance} />;
}

function Preview({ appearance }) {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [interaction, setInteraction] = useState({ id: 0, action: null });
  const [cameraReset, setCameraReset] = useState(0);
  const [cameraOrbit, setCameraOrbit] = useState({ id: 0, horizontal: 0, vertical: 0 });
  const pointers = useRef(new Map());
  const stageRef = useRef(null);
  const motionAllowed = useSceneMotionAllowed(stageRef);
  const helpId = useId();
  // A rejected lazy module is cached; retry uses a fresh lazy wrapper.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const AvatarScene = useMemo(() => lazy(() => import('../../avatar/AvatarScene')), [attempt]);
  const onReady = useCallback(() => setReady(true), []);
  const onFailure = useCallback((error) => {
    pointers.current.clear();
    setFailed({
      urls: [appearance?.url, ...Object.values(appearance?.textures || {})].filter((url) => url && error?.message?.includes(url)),
    });
  }, [appearance]);
  const showScene = appearance && !failed;
  const interactive = !!showScene && ready;

  const play = () => {
    if (interactive && motionAllowed) setInteraction((previous) => ({ id: previous.id + 1, action: REACTIONS[previous.id % REACTIONS.length] }));
  };
  const resetView = () => {
    pointers.current.clear();
    if (interactive) setCameraReset((value) => value + 1);
  };
  const pointerDown = (event) => {
    if (!interactive) return;
    const active = pointers.current;
    // OrbitControls owns capture on the real canvas. Observe its events without
    // putting a button or another capture target in the camera's way.
    if (active.size) active.forEach((pointer) => { pointer.tap = false; });
    active.set(event.pointerId, {
      x: event.clientX, y: event.clientY,
      tap: active.size === 0 && event.button === 0 && event.isPrimary !== false,
    });
  };
  const pointerMove = (event) => {
    const pointer = pointers.current.get(event.pointerId);
    if (pointer && Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y) > TAP_SLOP) pointer.tap = false;
  };
  const pointerUp = (event) => {
    pointerMove(event);
    const pointer = pointers.current.get(event.pointerId);
    pointers.current.delete(event.pointerId);
    if (pointer?.tap && event.button === 0) play();
  };
  const pointerCancel = (event) => {
    pointers.current.delete(event.pointerId);
  };
  const keyDown = (event) => {
    if (!interactive || event.altKey || event.ctrlKey || event.metaKey) return;
    const directions = {
      ArrowLeft: [1, 0], ArrowRight: [-1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1],
    };
    if (event.key === 'Home') {
      event.preventDefault();
      resetView();
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (!event.repeat) play();
    } else if (directions[event.key]) {
      event.preventDefault();
      const [horizontal, vertical] = directions[event.key];
      setCameraOrbit((previous) => ({ id: previous.id + 1, horizontal, vertical }));
    }
  };

  const retry = async () => {
    try {
      const { resetAvatarAssets } = await import('../../avatar/modelLoader');
      resetAvatarAssets(appearance, failed?.urls || []);
    } catch { /* Customization remains available without the optional preview. */ }
    setReady(false);
    setFailed(false);
    pointers.current.clear();
    setInteraction({ id: 0, action: null });
    setCameraReset(0);
    setCameraOrbit({ id: 0, horizontal: 0, vertical: 0 });
    setAttempt((value) => value + 1);
  };

  return (
    <div className="space-y-2">
      <div className="relative h-80 overflow-hidden rounded-2xl border border-ink-page-shadow bg-ink-page-aged focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sheikah-teal-deep"
        ref={stageRef} role="group" aria-label="Avatar view" aria-describedby={interactive ? helpId : undefined} tabIndex={interactive ? 0 : -1}
        aria-busy={!!showScene && !ready}
        onPointerDownCapture={pointerDown} onPointerMoveCapture={pointerMove} onPointerUpCapture={pointerUp}
        onPointerCancelCapture={pointerCancel} onLostPointerCaptureCapture={pointerCancel} onKeyDown={keyDown}>
        <div className="absolute inset-0" role="img" aria-label="Your Archer avatar">
          {showScene && <div className="absolute inset-0" aria-hidden="true">
            <AvatarBoundary key={attempt} onFailure={onFailure}>
              <Suspense fallback={null}>
                <AvatarScene appearance={appearance} interaction={interaction} cameraReset={cameraReset} cameraOrbit={cameraOrbit}
                  motionAllowed={motionAllowed} onReady={onReady} onUnavailable={onFailure} />
              </Suspense>
            </AvatarBoundary>
          </div>}
        </div>
        {(!showScene || !ready) && <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
          <UserRound size={64} className="text-sheikah-teal-deep" aria-hidden="true" />
          <p className="font-body text-body text-ink-secondary" role="status">
            {showScene ? 'Loading your avatar…' : 'The avatar preview is unavailable. You can still customize your look.'}
          </p>
          {failed && <Button size="sm" variant="secondary" onClick={retry}>Retry avatar preview</Button>}
        </div>}
      </div>
      {showScene && <>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" disabled={!interactive || !motionAllowed} onClick={play}>Play animation</Button>
          <Button size="sm" variant="ghost" disabled={!interactive} onClick={resetView}>Reset view</Button>
        </div>
        <p id={helpId} className="font-body text-caption text-ink-secondary">
          {motionAllowed ? 'Tap for an animation. Drag to look around.' : 'Drag to look around. Animations are paused.'}
          {' Scroll outside the preview.'}
          <span className="sr-only"> Focus the avatar view and use arrow keys to look around. Press Home to reset the view.{motionAllowed && ' Press Enter or Space to play an animation.'}</span>
        </p>
      </>}
    </div>
  );
}
