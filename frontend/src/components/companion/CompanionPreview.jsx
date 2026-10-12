import { Component, lazy, Suspense, useCallback, useId, useMemo, useState } from 'react';
import { Heart, RotateCcw } from 'lucide-react';
import Button from '../Button';
import RpgSprite from '../rpg/RpgSprite';
import { petSpriteKeys } from '../rpg/petSpriteKeys';
import { creatureLabel, resolveAppearance } from '../../companion/appearance';
import './companion.css';

class SceneBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) {
    if (import.meta.env.DEV) console.warn('Optional companion view unavailable.', error);
    this.props.onFailure(error);
  }
  render() { return this.state.failed ? null : this.props.children; }
}

export default function CompanionPreview({ creature, kind = 'pet', children }) {
  // Identity/stage changes remount local presentation. A greeting or preview
  // choice must never carry to another creature or change saved ownership.
  const identity = `${kind}:${creature?.id}:${creature?.evolved_to_mount === true}:${creature?.species?.sprite_key}:${creature?.potion?.slug}`;
  return <Preview key={identity} creature={creature} kind={kind}>{children}</Preview>;
}

function Preview({ creature, kind, children }) {
  const headingId = useId();
  const [enabled, setEnabled] = useState(false);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [greeting, setGreeting] = useState(0);
  const [animate, setAnimate] = useState(false);
  // Recreate the lazy wrapper after a failed chunk, whose rejection React caches.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const CompanionScene = useMemo(() => lazy(() => import('../../companion/CompanionScene')), [attempt]);
  const appearance = import.meta.env.VITE_COMPANION_3D === 'false' ? null : resolveAppearance(creature, kind);
  const onReady = useCallback(() => setReady(true), []);
  const onUnavailable = useCallback(() => setFailed({ urls: [] }), []);
  const onAssetFailure = useCallback((error) => setFailed({
    urls: [appearance?.url, appearance?.woodland?.url].filter((url) => url && error?.message?.includes(url)),
  }), [appearance?.url, appearance?.woodland?.url]);
  const label = creatureLabel(creature);
  const showScene = enabled && appearance && !failed;
  const mount = kind === 'mount' || creature?.evolved_to_mount === true;
  const sprite = kind === 'mount'
    ? { spriteKey: creature?.species?.sprite_key && `${creature.species.sprite_key}-mount`, fallbackSpriteKey: creature?.species?.sprite_key }
    : petSpriteKeys(creature);

  const startScene = async () => {
    if (failed?.urls?.length) {
      // Clear a rejected model load as well as resetting the error boundary.
      // Failed optional chunk downloads can then be attempted again too.
      try {
        const { resetModels } = await import('../../companion/modelLoader');
        resetModels(failed.urls);
      } catch { /* The DOM companion remains usable if the network is down. */ }
    }
    setReady(false);
    setFailed(false);
    setAttempt((value) => value + 1);
    setEnabled(true);
  };

  return (
    <section className="companion-preview" aria-labelledby={headingId}>
      <div className="companion-preview-heading">
        <div>
          <p className="text-caption font-semibold text-sheikah-teal-deep">Your companion</p>
          <h2 id={headingId} className="text-lede font-bold text-ink-primary">{label || 'Choose a companion'}</h2>
          {creature && <p className="text-caption text-ink-secondary">{mount ? 'Evolved companion' : `${creature.growth_points ?? 0}/100 growth`}{creature.is_active ? ' · Active' : ' · Preview'}</p>}
        </div>
        {appearance && <Button size="sm" variant="secondary" onClick={showScene ? () => setEnabled(false) : startScene}>{showScene ? 'Use 2D view' : failed ? 'Retry 3D view' : 'Show 3D view'}</Button>}
      </div>

      <div className="companion-preview-stage" aria-busy={showScene && !ready}>
        {(!showScene || !ready) && <div className="companion-preview-portrait">
          {creature ? <RpgSprite {...sprite} icon={creature.species?.icon} size={160} alt={label} potionSlug={creature.potion?.slug} dim={!mount && creature.happiness_level !== 'happy' ? creature.happiness_level : null} /> : <Heart size={48} aria-hidden="true" />}
        </div>}
        {showScene && <div className="companion-preview-canvas" aria-hidden="true">
          <SceneBoundary key={attempt} onFailure={onAssetFailure}>
            <Suspense fallback={null}>
              <CompanionScene appearance={appearance} greeting={greeting} animate={animate} onReady={onReady} onUnavailable={onUnavailable} />
            </Suspense>
          </SceneBoundary>
        </div>}
        <p className="companion-preview-message" role="status" aria-live="polite">
          {failed ? 'The 3D view could not load. Your companion and all controls are still available.'
            : showScene && !ready ? 'Loading the woodland…'
              : greeting ? `Hello, ${label}! A little greeting, just for fun.`
                : creature ? 'A little company while you grow.' : 'Hatch a pet, then set it active to see it here.'}
        </p>
      </div>

      {creature && <div className="companion-preview-actions">
        <Button size="sm" variant="secondary" onClick={() => setGreeting((value) => value + 1)}><Heart size={16} aria-hidden="true" /> Say hello</Button>
        {showScene && <>
          <label className="companion-motion-control"><input type="checkbox" checked={animate} onChange={(event) => setAnimate(event.target.checked)} /> Animate companion</label>
          <Button size="sm" variant="ghost" onClick={startScene} aria-label="Reset companion view"><RotateCcw size={16} aria-hidden="true" /> Reset view</Button>
        </>}
      </div>}
      {children}
    </section>
  );
}
