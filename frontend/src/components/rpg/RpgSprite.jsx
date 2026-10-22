import { useState } from 'react';
import { useSpriteCatalog } from '../../providers/spriteCatalog.context';
import { getLicensedRpgSprite } from '../../storybook/licensedRpgSprites';
import { resolveRosterPortrait } from '../../companion/sharedRosterRelease';
import { resolveElementalPortrait } from '../../companion/sharedElementalPortraits';

const SIZE_TO_TEXT_CLASS = {
  24: 'text-xl',
  32: 'text-2xl',
  40: 'text-3xl',
  48: 'text-4xl',
  56: 'text-5xl',
  64: 'text-6xl',
  80: 'text-7xl',
  96: 'text-8xl',
};

// Potion-driven recolor filters. Applied to pet/mount sprites so one base
// sprite covers N potion variants (Dragon + fire potion reads as a fire
// dragon without a separate sprite). Base potion is the "natural" color,
// so we don't filter it.
const POTION_FILTERS = {
  fire:    'hue-rotate(330deg) saturate(1.5) brightness(1.1)',
  ice:     'hue-rotate(190deg) saturate(1.2) brightness(1.05)',
  shadow:  'hue-rotate(260deg) saturate(1.3) brightness(0.7)',
  golden:  'hue-rotate(40deg)  saturate(1.4) brightness(1.15)',
  cosmic:  'hue-rotate(230deg) saturate(1.4) brightness(0.9) contrast(1.1)',
};

// These prepared families need exact elemental portraits from the asset
// release. A CSS recolor of a Base image cannot stand in for that artwork.
const ELEMENTAL_PORTRAIT_KEYS = new Set([
  'cute-chick', 'cute-chick-fledgling', 'cute-chick-mount',
  'meshtint-wolf', 'meshtint-wolf-middle', 'meshtint-wolf-mount',
  'meshtint-dragon', 'meshtint-dragon-middle', 'meshtint-dragon-mount',
  'meshtint-mushroom', 'meshtint-mushroom-middle', 'meshtint-mushroom-mount',
]);

// Gentle-nudge dimming applied to pet sprites whose happiness has slipped.
// Purely visual — never penalizes coins / XP / drops / growth. ``happy`` is
// the default state and renders unaffected so the sprite stays vibrant.
const DIM_FILTERS = {
  bored: 'grayscale(0.25) opacity(0.85)',
  stale: 'grayscale(0.5) opacity(0.7)',
  away:  'grayscale(0.75) opacity(0.55)',
};

/**
 * Renders an RPG entity icon. Branches on sprite metadata:
 *  - static (frames=1): plain <img>
 *  - animated (frames>1): <span> with CSS background-position animation
 *  - unknown slug or catalog still loading: emoji fallback
 *
 * ``fallbackSpriteKey`` is tried when ``spriteKey`` isn't in the catalog.
 * Use case: mount sprites named ``{species}-mount`` fall back to the
 * base species sprite for species we haven't drawn evolved forms of yet.
 *
 * Registered Fire/Ice appearances require their exact stage portraits,
 * including families awaiting artwork adoption.
 * ``potionSlug`` retains legacy hue filters for other species/appearances.
 */
export default function RpgSprite({
  spriteKey,
  fallbackSpriteKey,
  icon,
  size = 32,
  className = '',
  alt = '',
  potionSlug = null,
  dim = null,
  rendering = 'smooth',
}) {
  const { getSpriteMeta } = useSpriteCatalog();
  // Bind failures to the URL that failed. A late error from the previous
  // portrait must not hide a new species or a refreshed catalog URL.
  const [failedUrls, setFailedUrls] = useState(() => new Set());
  const exactElemental = ['fire', 'ice'].includes(potionSlug)
    && [spriteKey, fallbackSpriteKey].some((key) => ELEMENTAL_PORTRAIT_KEYS.has(key));
  const candidates = exactElemental ? [resolveElementalPortrait(spriteKey, potionSlug)]
    : [spriteKey, fallbackSpriteKey].filter(Boolean).flatMap((key) => [
      resolveRosterPortrait(key, potionSlug, size > 96 ? 'native' : 'icon'),
      getLicensedRpgSprite(key, size > 96 ? 'native' : 'icon'), getSpriteMeta(key),
    ]);
  const meta = candidates
    .find((candidate) => candidate?.url && !failedUrls.has(candidate.url));
  const onImageError = () => setFailedUrls((previous) => new Set(previous).add(meta.url));
  const imageRendering = rendering === 'pixelated' ? 'pixelated' : 'auto';
  const potionFilter = potionSlug && !exactElemental ? POTION_FILTERS[potionSlug] : undefined;
  const dimFilter = dim ? DIM_FILTERS[dim] : undefined;
  const composedFilter = [potionFilter, dimFilter].filter(Boolean).join(' ') || undefined;

  if (meta && meta.frames === 1) {
    return (
      <img
        key={meta.url}
        src={meta.url}
        alt={alt || spriteKey || 'sprite'}
        width={size}
        height={size}
        loading="lazy"
        onError={onImageError}
        data-dim={dim || undefined}
        style={{
          imageRendering,
          objectFit: 'contain',
          width: size,
          height: size,
          filter: composedFilter,
        }}
        className={className}
      />
    );
  }

  if (meta && meta.frames > 1) {
    const duration = (meta.frames / meta.fps).toFixed(3);
    const totalWidth = meta.frames * size;
    // Canonical sprite-sheet animation: endX is -N × size (off-sheet,
    // transparent) and `steps(N)` (= jump-end) holds each of the N frames
    // for 1/N of the duration. At t=1 the animation jumps to endX but
    // immediately loops back to 0, so the off-sheet position is never
    // visible. The previous `steps(N, jump-none)` + endX=-(N-1)×size
    // technique held only the first N-1 frames for 1/(N-1) duration
    // each and flashed frame N-1 briefly at the loop boundary — which
    // looked to users like a bleed/ghosting artifact.
    const endX = -meta.frames * size;
    return (
      <span
        role="img"
        aria-label={alt || spriteKey || 'sprite'}
        data-dim={dim || undefined}
        className={`inline-block ${className}`}
        style={{
          width: size,
          height: size,
          backgroundImage: `url(${meta.url})`,
          backgroundSize: `${totalWidth}px ${size}px`,
          backgroundPositionX: 0,
          imageRendering,
          filter: composedFilter,
          '--sprite-end-x': `${endX}px`,
          animation: `sprite-cycle ${duration}s steps(${meta.frames}) infinite`,
        }}
      >
        {/* CSS backgrounds have no error event. This hidden probe lets a
            failed strip use the same fallback as a failed static portrait. */}
        <img key={meta.url} src={meta.url} alt="" aria-hidden="true" className="hidden" onError={onImageError} />
      </span>
    );
  }

  // Emoji fallback
  const cls = SIZE_TO_TEXT_CLASS[size];
  if (cls) {
    return (
      <span
        className={`leading-none inline-block ${cls} ${className}`}
        role="img"
        aria-label={alt || spriteKey || 'Item'}
        data-dim={dim || undefined}
        style={composedFilter ? { filter: composedFilter } : undefined}
      >
        <span aria-hidden="true">{icon || '✨'}</span>
      </span>
    );
  }
  return (
    <span
      className={`leading-none inline-block ${className}`}
      style={{ fontSize: size, filter: composedFilter }}
      role="img"
      aria-label={alt || spriteKey || 'Item'}
      data-dim={dim || undefined}
    >
      <span aria-hidden="true">{icon || '✨'}</span>
    </span>
  );
}
