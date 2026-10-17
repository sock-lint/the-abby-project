import { Component, lazy, Suspense, useCallback, useMemo, useRef, useState } from 'react';
import { Sprout } from 'lucide-react';
import Button from '../components/Button';
import useSceneMotionAllowed from '../companion/useSceneMotionAllowed';
import { stagedPedestalRelease } from './pedestalRelease';
import { PEDESTAL_EGG_ASSETS, pedestalPlaybackIdentity } from './pedestal.constants';

class PreviewBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) { this.props.onFailure(error); }
  render() { return this.state.failed ? null : this.props.children; }
}

export default function PedestalPreview({ eggAssetId = 'normal-egg', animate = true, className = '', stageClassName = 'h-80', staged }) {
  const release = useMemo(() => staged === undefined ? stagedPedestalRelease() : staged, [staged]);
  return <Preview key={pedestalPlaybackIdentity(release, eggAssetId)} staged={release} eggAssetId={eggAssetId}
    animate={animate} className={className} stageClassName={stageClassName} />;
}

function Preview({ staged, eggAssetId, animate, className, stageClassName }) {
  const [enabled, setEnabled] = useState(true);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const stageRef = useRef(null);
  const motionAllowed = useSceneMotionAllowed(stageRef);
  // A rejected lazy import is cached; retry needs a fresh lazy component.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const Scene = useMemo(() => lazy(() => import('./PedestalScene')), [attempt]);
  const onReady = useCallback(() => setReady(true), []);
  const onFailure = useCallback(() => { setFailed(true); setReady(false); }, []);
  const supported = staged && (eggAssetId === null || PEDESTAL_EGG_ASSETS.includes(eggAssetId));
  const showScene = supported && enabled && !failed;
  const label = eggAssetId === null ? 'Decorative woodland pedestal' : 'Decorative egg on a woodland pedestal';
  const retry = () => { setReady(false); setFailed(false); setAttempt((value) => value + 1); };
  const toggle = () => { setEnabled((value) => !value); setReady(false); };
  return <div className={`space-y-2 ${className}`}>
    <div ref={stageRef} data-display-state={!enabled ? 'off' : !showScene ? 'unavailable' : ready ? 'ready' : 'loading'}
      className={`relative ${stageClassName} w-full overflow-hidden rounded-2xl border border-ink-page-shadow bg-ink-page-aged`}
      role="group" aria-label="Woodland display" aria-busy={!!showScene && !ready}>
      <div className="absolute inset-0" role="img" aria-label={label}>
        {showScene && <div className="absolute inset-0" aria-hidden="true">
          <PreviewBoundary key={attempt} onFailure={onFailure}>
            <Suspense fallback={null}><Scene staged={staged} eggAssetId={eggAssetId} motionAllowed={animate && motionAllowed}
              onReady={onReady} onUnavailable={onFailure} /></Suspense>
          </PreviewBoundary>
        </div>}
      </div>
      {(!showScene || !ready) && <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
        <Sprout size={48} className="text-sheikah-teal-deep" aria-hidden="true" />
        <p role="status" className="font-body text-body text-ink-secondary">
          {showScene ? 'Loading the woodland display…' : !enabled ? '3D display is off.' : 'The decorative 3D display is unavailable.'}
        </p>
      </div>}
    </div>
    {supported && <div className="flex flex-wrap gap-2">
      <Button variant="ghost" size="sm" aria-pressed={enabled} onClick={toggle}>{enabled ? 'Turn off 3D display' : 'Turn on 3D display'}</Button>
      {failed && enabled && <Button variant="secondary" size="sm" onClick={retry}>Retry 3D display</Button>}
    </div>}
    {showScene && ready && (!animate || !motionAllowed) && <p className="text-caption text-ink-secondary">Animations are paused.</p>}
  </div>;
}
