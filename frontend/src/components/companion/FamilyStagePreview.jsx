import { Component, lazy, Suspense, useCallback, useMemo, useState } from 'react';
import Button from '../Button';
import CatalogIcon from '../rpg/CatalogIcon';
import RpgSprite from '../rpg/RpgSprite';
import CompanionMotionControls from './CompanionMotionControls';
import { COMPANION_STAGES, eggSpecies } from '../../companion/lifecycle';
import { rosterEggFamily, resolveRosterPreviewAppearance } from '../../companion/sharedRosterRelease';
import { resolveSharedBirdPreviewAppearance } from '../../companion/sharedBirdRelease';
import { resolveElementalPreviewAppearance } from '../../companion/sharedElementalRelease';
import { petSpriteKeys } from '../rpg/petSpriteKeys';
import usePrefersReducedMotion from '../../hooks/usePrefersReducedMotion';
import PedestalPreview from '../../pedestal/PedestalPreview';

class PreviewBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) { this.props.onFailure(error); }
  render() { return this.state.failed ? null : this.props.children; }
}

export default function FamilyStagePreview({ item, potion }) {
  const family = rosterEggFamily(item);
  const retained = item?.item_type === 'egg' && item.slug === 'chick-egg' && item.pet_species_slug === 'chick' && item.metadata?.species === 'chick';
  const [stage, setStage] = useState('egg');
  if (!family && !retained) return <div className="flex h-48 items-center justify-center"><RpgSprite icon="🥚" size={96} alt={item?.name || 'Egg'} /></div>;
  const element = potion?.slug && potion.slug !== 'base' ? potion.name || potion.slug : null;
  const form = family?.stages[stage]?.name || { baby: 'Chick', middle: 'Fledgling', grown: 'Bird' }[stage];
  const name = stage === 'egg' ? item.name || 'Egg' : `${element ? `${element} ` : ''}${form}`;
  return <section className="space-y-3" aria-label="Family artwork preview">
    <div className="flex flex-wrap gap-2" role="group" aria-label="Preview growth stage">
      {COMPANION_STAGES.map(({ id, label }) => <Button key={id} size="sm" variant={stage === id ? 'secondary' : 'ghost'} aria-pressed={stage === id} onClick={() => setStage(id)}>{label}</Button>)}
    </div>
    <StagePreview key={`${item.id}:${stage}:${potion?.slug || 'base'}`} item={item} family={family} retained={retained} stage={stage} name={name} element={element} potion={potion} />
    {stage === 'egg' && element && <p className="text-caption text-ink-secondary">The egg keeps its natural appearance. The {element} appearance begins after hatching.</p>}
    <p className="text-caption text-ink-secondary">Artwork preview. Hatching and growth are saved through your pet care actions.</p>
  </section>;
}

function StagePreview({ item, family, retained, stage, name, element, potion }) {
  const [enabled, setEnabled] = useState(false), [ready, setReady] = useState(false), [failed, setFailed] = useState(false);
  const [animate, setAnimate] = useState(true), [interaction, setInteraction] = useState(null), [attempt, setAttempt] = useState(0);
  const [playback, setPlayback] = useState(null);
  const reducedMotion = usePrefersReducedMotion();
  // A separate immutable release binds each elemental stage. Missing exact
  // art must never become a Base model or CSS-tinted preview.
  const elementalStage = !!element && stage !== 'egg';
  const appearance = useMemo(() => elementalStage ? resolveElementalPreviewAppearance(item, stage, potion)
    : retained ? resolveSharedBirdPreviewAppearance(item, stage) : resolveRosterPreviewAppearance(item, stage), [item, retained, stage, elementalStage, potion]);
  // A retry owns a fresh lazy wrapper so rejected chunk downloads can recover.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const Scene = useMemo(() => lazy(() => import('../../companion/CompanionScene')), [attempt]);
  const onReady = useCallback(() => setReady(true), []), onFailure = useCallback(() => setFailed(true), []);
  const onPlaybackState = useCallback((value) => setPlayback(value), []);
  const spriteKey = retained ? { egg: 'chick-egg', baby: 'cute-chick', middle: 'cute-chick-fledgling', grown: 'cute-chick-mount' }[stage]
    : stage === 'middle' ? `${family.sprite_key}-middle` : stage === 'grown' ? `${family.sprite_key}-mount` : family.sprite_key;
  const elementalSpriteKey = elementalStage && ['fire', 'ice'].includes(potion?.slug)
    ? petSpriteKeys({ id: item.id, species: eggSpecies(item), potion, lifecycle_stage: stage, evolved_to_mount: stage === 'grown' }).spriteKey : null;
  const shown = enabled && !failed;
  const turnOn = () => { setFailed(false); setReady(false); setAttempt((value) => value + 1); setEnabled(true); };
  return <div className="space-y-2">
    <h4 className="text-body font-semibold text-ink-primary">{name}</h4>
    <div className="relative h-80 overflow-hidden rounded-2xl border border-ink-page-shadow bg-ink-page-aged" role="group" aria-label={`${name} artwork preview`} aria-busy={!!(shown && appearance && !ready)}>
      {(!shown || !ready || !appearance) && <div className="absolute inset-0 flex items-center justify-center">
        {stage === 'egg' && family ? <CatalogIcon assetId={family.egg.portrait_asset_id} icon="🥚" alt={name} size={160} />
          : <RpgSprite spriteKey={elementalStage ? elementalSpriteKey : spriteKey} potionSlug={elementalStage ? potion?.slug : undefined}
            icon={stage === 'egg' ? '🥚' : '🐾'} alt={elementalStage && !appearance ? `${name} artwork unavailable` : name} size={160} />}
      </div>}
      {shown && appearance && <div className="absolute inset-0" aria-hidden="true"><PreviewBoundary key={attempt} onFailure={onFailure}><Suspense fallback={null}>
        <Scene appearance={appearance} animate={animate && !reducedMotion} interaction={interaction} onReady={onReady} onUnavailable={onFailure} onPlaybackState={onPlaybackState} />
      </Suspense></PreviewBoundary></div>}
      {shown && retained && stage === 'egg' && <div className="absolute inset-0"><PedestalPreview animate={animate && !reducedMotion} stageClassName="h-80" /></div>}
    </div>
    {elementalStage && !appearance && <p role="status" className="text-caption text-ink-secondary">{element} artwork is not available yet. You can still inspect the growth stages and choose your ingredients.</p>}
    {(appearance || (retained && stage === 'egg')) && <div className="flex flex-wrap items-center gap-3">
      <Button variant="secondary" size="sm" onClick={enabled && !failed ? () => setEnabled(false) : turnOn}>{failed ? 'Retry 3D preview' : enabled ? 'Use portrait' : 'Show 3D preview'}</Button>
      {enabled && <label className="text-caption text-ink-secondary"><input type="checkbox" checked={animate} onChange={(event) => setAnimate(event.target.checked)} /> Animate preview</label>}
    </div>}
    {failed && <p role="status" className="text-caption text-ink-secondary">The 3D preview could not load. You can still view the portrait and hatch your pet.</p>}
    {shown && appearance && <p role="status" aria-label="Family preview playback" className="text-caption text-ink-secondary"
      data-playback-status={playback?.status || 'loading'} data-variant-id={playback?.variantId} data-motion-action={playback?.action} data-stage={playback?.stage || stage}>
      {playback?.status === 'idle' ? 'Resting.' : playback?.status === 'playing' ? `Playing ${appearance.motions.find((motion) => motion.action === playback.action)?.label || 'native motion'}.` : 'Loading preview…'}
    </p>}
    {appearance?.motions?.length > 0 && <CompanionMotionControls motions={appearance.motions} disabled={!shown || !ready || !animate || reducedMotion} onPlay={(motion) => setInteraction((previous) => ({ id: (previous?.id || 0) + 1, action: motion.id }))} />}
  </div>;
}
