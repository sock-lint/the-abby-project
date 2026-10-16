import { Component, lazy, Suspense, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Heart, MoveUp, RotateCcw, Settings2, Sparkles } from 'lucide-react';
import Button from '../Button';
import RpgSprite from '../rpg/RpgSprite';
import { petSpriteKeys } from '../rpg/petSpriteKeys';
import { creatureLabel, resolveAppearance } from '../../companion/appearance';
import CompanionMotionControls from './CompanionMotionControls';
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

export default function CompanionPreview({ creature, kind = 'pet', variant = 'preview', ...props }) {
  const identity = `${variant}:${kind}:${creature?.id}:${creature?.species?.slug}:${creature?.species?.sprite_key}:${creature?.potion?.slug}`;
  return <OwnedPreview key={identity} creature={creature} kind={kind} variant={variant} {...props} />;
}

function OwnedPreview({ creature, kind, variant, ...props }) {
  const [enabled, setEnabled] = useState(variant === 'primary');
  const [animate, setAnimate] = useState(variant === 'primary');
  const [attempt, setAttempt] = useState(0);
  const bird = creature?.species?.slug === 'chick' && creature?.species?.sprite_key === 'cute-chick' && creature?.potion?.slug === 'base';
  const stage = bird && ['chick', 'fledgling', 'bird'].includes(creature?.evolution_stage) ? creature.evolution_stage : null;
  const [observed, setObserved] = useState({ stage, count: 0, evolution: null });
  if (observed.stage !== stage) {
    const forward = (observed.stage === 'chick' && (stage === 'fledgling' || stage === 'bird')) || (observed.stage === 'fledgling' && stage === 'bird');
    setObserved({ stage, count: observed.count + 1, evolution: forward && enabled ? { id: observed.count + 1, from: observed.stage, to: stage } : null });
  }
  // Stage changes reset transient greetings/loading and invalidate old callbacks,
  // while retaining this creature's explicit display and motion preferences.
  const identity = `${stage}:${creature?.evolved_to_mount === true}:${attempt}`;
  return <Preview key={identity} creature={creature} kind={kind} variant={variant} stage={stage}
    enabled={enabled} setEnabled={setEnabled} animate={animate} setAnimate={setAnimate}
    evolution={observed.evolution} restartScene={() => {
      setObserved((previous) => ({ ...previous, evolution: null }));
      setEnabled(true);
      setAttempt((previous) => previous + 1);
    }} {...props} />;
}

function Preview({ creature, kind, variant, stage, enabled, setEnabled, animate, setAnimate, evolution, restartScene, kicker = 'Your companion', summary, onInteract, interactionLabel, reaction, onPresentationChange, children }) {
  const primary = variant === 'primary';
  const headingId = useId();
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [greeting, setGreeting] = useState(0);
  const [interaction, setInteraction] = useState(null);
  const [playback, setPlayback] = useState(null);
  // A retry remounts this component, recreating React's rejected lazy wrapper.
  const CompanionScene = useMemo(() => lazy(() => import('../../companion/CompanionScene')), []);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const appearance = useMemo(() => import.meta.env.VITE_COMPANION_3D === 'false' ? null : resolveAppearance(creature, kind), [creature, kind]);
  const onReady = useCallback(() => setReady(true), []);
  const onUnavailable = useCallback(() => setFailed({ urls: [] }), []);
  const onPlaybackState = useCallback((state) => setPlayback(state), []);
  const onAssetFailure = useCallback((error) => setFailed({
    urls: [appearance?.url, appearance?.woodland?.url, ...Object.values(appearance?.interactions || {}).map((take) => take.url)].filter((url) => url && error?.message?.includes(url)),
  }), [appearance]);
  const label = creatureLabel(creature);
  const name = creature?.name?.trim() || label;
  const showScene = enabled && appearance && !failed;
  useEffect(() => {
    onPresentationChange?.({ creatureId: creature?.id, sharedBirdReady: !!(showScene && ready && appearance?.pipeline === 'abby-assets-bird') });
  }, [appearance?.pipeline, creature?.id, onPresentationChange, ready, showScene]);
  const mount = kind === 'mount' || creature?.evolved_to_mount === true;
  const sprite = kind === 'mount'
    ? { spriteKey: creature?.species?.sprite_key && `${creature.species.sprite_key}-mount`, fallbackSpriteKey: creature?.species?.sprite_key }
    : petSpriteKeys(creature);
  const playTogether = (action) => {
    const messages = {
      hello: `${name} is happy to see you.`,
      play: appearance?.key === 'bird' ? `${name} stretches their wings and takes a little flight.`
        : appearance?.key === 'fledgling' ? `${name} takes a little walk with you.` : `${name} hops along with you.`,
      left: `${name} looks around the clearing with you.`,
      right: `${name} looks around the clearing with you.`,
    };
    setInteraction((previous) => ({ id: (previous?.id || 0) + 1, action, message: messages[action] }));
  };
  const playMotion = (motion) => {
    setInteraction((previous) => ({ id: (previous?.id || 0) + 1, action: motion.id, message: `${name}: ${motion.label}.` }));
  };

  const startScene = async () => {
    if (failed?.urls?.length) {
      // Clear a rejected model load as well as resetting the error boundary.
      // Failed optional chunk downloads can then be attempted again too.
      try {
        const { resetModels } = await import('../../companion/modelLoader');
        resetModels(failed.urls, [appearance.url, ...Object.values(appearance.interactions || {}).map((take) => take.url)]);
      } catch { /* The DOM companion remains usable if the network is down. */ }
    }
    if (mounted.current) restartScene();
  };

  return (
    <section className={`companion-preview${primary ? ' companion-preview-primary' : ''}`} aria-labelledby={headingId}>
      <div className="companion-preview-heading">
        <div>
          <p className="text-caption font-semibold text-sheikah-teal-deep">{kicker}</p>
          <h2 id={headingId} className={`${primary ? 'companion-primary-name text-2xl sm:text-3xl' : 'text-lede'} font-bold text-ink-primary`}>{(primary ? name : label) || 'Choose a companion'}</h2>
          {creature && <p className="text-caption text-ink-secondary">{primary && name !== label ? `${label} · ` : ''}{stage ? `${stage[0].toUpperCase()}${stage.slice(1)} · ` : ''}{mount ? 'Evolved companion' : `${creature.growth_points ?? 0}/100 growth`}{!primary && (creature.is_active ? ' · Active' : ' · Preview')}</p>}
          {primary && summary && <p className="companion-primary-summary">{summary}</p>}
        </div>
        {appearance && (primary ? <details className="companion-view-settings">
          <summary><Settings2 size={16} aria-hidden="true" /> View</summary>
          <div className="companion-view-options">
            <div role="group" aria-label="Companion display">
              <Button size="sm" variant="ghost" aria-pressed={!showScene} onClick={() => setEnabled(false)}>2D portrait</Button>
              <Button size="sm" variant="ghost" aria-pressed={!!showScene} onClick={startScene}>{failed ? 'Retry 3D woodland' : '3D woodland'}</Button>
            </div>
            {showScene && <label className="companion-motion-control"><input type="checkbox" checked={animate} onChange={(event) => setAnimate(event.target.checked)} /> Animate companion</label>}
          </div>
        </details> : <Button size="sm" variant="secondary" onClick={showScene ? () => setEnabled(false) : startScene}>{showScene ? 'Use 2D view' : failed ? 'Retry 3D view' : 'Show 3D view'}</Button>)}
      </div>

      <div className="companion-preview-stage" aria-busy={showScene && !ready}>
        {(!showScene || !ready) && <div className="companion-preview-portrait">
          {creature ? <RpgSprite {...sprite} icon={creature.species?.icon} size={160} alt={primary ? `${name}, your companion` : label} potionSlug={creature.potion?.slug} dim={!mount && creature.happiness_level !== 'happy' ? creature.happiness_level : null} /> : <Heart size={48} aria-hidden="true" />}
        </div>}
        {showScene && <div className="companion-preview-canvas" aria-hidden="true">
          <SceneBoundary onFailure={onAssetFailure}>
            <Suspense fallback={null}>
              <CompanionScene appearance={appearance} greeting={greeting} interaction={interaction} evolution={evolution} reaction={reaction} animate={animate} onReady={onReady} onUnavailable={onUnavailable} onPlaybackState={onPlaybackState} />
            </Suspense>
          </SceneBoundary>
        </div>}
        {primary && creature && <button type="button" className="companion-stage-interaction" onClick={onInteract || (() => playTogether('hello'))} aria-label={interactionLabel || `Say hello to ${name}`}>
          {!failed && (!showScene || ready) && <span className="companion-interaction-hint">{interactionLabel || 'Tap to say hello'}</span>}
        </button>}
        {(!primary || failed || (showScene && !ready)) && <p className="companion-preview-message" role="status" aria-live="polite">
          {failed ? 'The 3D view could not load. Your companion and all controls are still available.'
            : showScene && !ready ? 'Loading the woodland…'
              : greeting ? `Hello, ${label}! A little greeting, just for fun.`
                : creature ? 'A little company while you grow.' : 'Hatch a pet, then set it active to see it here.'}
        </p>}
      </div>

      {primary && creature && <div className="companion-play-area">
        <div className="companion-play-controls" role="group" aria-label={`Spend time with ${name}`}>
          <Button size="sm" variant="secondary" onClick={() => playTogether('hello')}><Heart size={16} aria-hidden="true" /> Say hello</Button>
          {appearance?.interactions?.play && <Button size="sm" variant="secondary" disabled={!showScene || !ready} onClick={() => playTogether('play')}><MoveUp size={16} aria-hidden="true" />{appearance.key === 'bird' ? 'Fly together' : appearance.key === 'fledgling' ? 'Walk together' : 'Hop together'}</Button>}
          {appearance?.interactions?.left && appearance?.interactions?.right && <Button size="sm" variant="secondary" disabled={!showScene || !ready} onClick={() => playTogether(interaction?.action === 'left' ? 'right' : 'left')}><Sparkles size={16} aria-hidden="true" /> Look around</Button>}
        </div>
        <p className="companion-play-response" role="status" aria-live="polite">{interaction?.message || `Take a little break with ${name}.`}</p>
      </div>}

      {!primary && creature && <div className="companion-preview-actions">
        <Button size="sm" variant="secondary" onClick={() => setGreeting((value) => value + 1)}><Heart size={16} aria-hidden="true" /> Say hello</Button>
        {showScene && <>
          <label className="companion-motion-control"><input type="checkbox" checked={animate} onChange={(event) => setAnimate(event.target.checked)} /> Animate companion</label>
          <Button size="sm" variant="ghost" onClick={startScene} aria-label="Reset companion view"><RotateCcw size={16} aria-hidden="true" /> Reset view</Button>
        </>}
      </div>}
      {appearance?.motions?.length > 0 && <CompanionMotionControls motions={appearance.motions} disabled={!showScene || !ready} onPlay={playMotion} />}
      {appearance?.pipeline === 'abby-assets-bird' && showScene && <p className="companion-playback-status" role="status" aria-label="Companion playback" aria-live="polite"
        data-playback-status={playback?.status || 'loading'} data-variant-id={playback?.variantId} data-stage={playback?.stage || stage}>
        {playback?.status === 'idle' ? 'Your companion is resting.'
          : playback?.status === 'evolving' ? 'Your companion is growing into their next stage.'
            : playback?.status === 'playing' ? `Playing ${appearance.motions.find((motion) => motion.id === playback.variantId)?.label || 'companion motion'}.`
              : 'Loading companion motion…'}
      </p>}
      {children}
    </section>
  );
}
