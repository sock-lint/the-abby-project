import { Component, lazy, Suspense, useCallback, useMemo, useState } from 'react';
import { UserRound } from 'lucide-react';
import Button from '../Button';
import { resolveAvatarAppearance } from '../../avatar/appearance';

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
  // A rejected lazy module is cached; retry uses a fresh lazy wrapper.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const AvatarScene = useMemo(() => lazy(() => import('../../avatar/AvatarScene')), [attempt]);
  const onReady = useCallback(() => setReady(true), []);
  const onFailure = useCallback((error) => setFailed({
    urls: [appearance?.url, ...Object.values(appearance?.textures || {})].filter((url) => url && error?.message?.includes(url)),
  }), [appearance]);
  const showScene = appearance && !failed;

  const retry = async () => {
    try {
      const { resetAvatarAssets } = await import('../../avatar/modelLoader');
      resetAvatarAssets(appearance, failed?.urls || []);
    } catch { /* Customization remains available without the optional preview. */ }
    setReady(false);
    setFailed(false);
    setAttempt((value) => value + 1);
  };

  return (
    <div className="relative h-80 overflow-hidden rounded-2xl border border-ink-page-shadow bg-ink-page-aged" aria-busy={!!showScene && !ready}>
      <div className="absolute inset-0" role="img" aria-label="Your Archer avatar">
      {showScene && <div className="absolute inset-0" aria-hidden="true">
        <AvatarBoundary key={attempt} onFailure={onFailure}>
          <Suspense fallback={null}>
            <AvatarScene appearance={appearance} onReady={onReady} onUnavailable={onFailure} />
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
  );
}
