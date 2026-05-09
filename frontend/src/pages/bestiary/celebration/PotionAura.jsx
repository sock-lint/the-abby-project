// Potion-tinted aura ring used behind hatched/evolving creatures.
// Mirrors RpgSprite's potion vocabulary so the glow color matches the
// hue-rotated sprite filter.
const POTION_AURA_COLORS = {
  fire:    'rgba(245, 90, 60, 0.55)',
  ice:     'rgba(110, 175, 230, 0.55)',
  shadow:  'rgba(150, 100, 200, 0.55)',
  golden:  'rgba(245, 200, 80, 0.55)',
  cosmic:  'rgba(170, 130, 255, 0.6)',
};
const FALLBACK_AURA = 'rgba(120, 200, 180, 0.45)';

/**
 * Soft radial aura behind a creature sprite. Keyed off ``potionSlug`` so
 * a fire dragon glows red and an ice dragon glows blue. ``intensity``
 * (0–1) is animated by the parent across phases — the aura uses a CSS
 * opacity transition so reduced-motion users still see the static halo
 * without a fade.
 */
export default function PotionAura({ potionSlug, size = 160, intensity = 1 }) {
  const color = POTION_AURA_COLORS[potionSlug] || FALLBACK_AURA;
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute"
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
        opacity: intensity,
        transition: 'opacity 220ms ease-out',
      }}
    />
  );
}
