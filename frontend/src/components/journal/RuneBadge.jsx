/**
 * RuneBadge — small glyph-framed badge for status, rarity, and category tags.
 * Used as the parchment-era replacement for the old amber/tinted pill badges.
 *
 * Props:
 *   tone    - visual tone: "teal" | "moss" | "ember" | "royal" | "gold" | "ink"
 *   variant - "filled" | "outlined" (default "filled")
 *   size    - "sm" | "md" (default "sm")
 */
export default function RuneBadge({
  children,
  tone = 'teal',
  variant = 'filled',
  size = 'sm',
  icon,
  className = '',
}) {
  const tones = {
    teal: {
      filled: 'bg-sheikah-teal/20 text-sheikah-teal-deep border-sheikah-teal/50',
      outlined: 'text-sheikah-teal-deep border-sheikah-teal/60',
    },
    moss: {
      filled: 'bg-moss/20 text-moss border-moss/50',
      outlined: 'text-moss border-moss/60',
    },
    ember: {
      filled: 'bg-ember/20 text-ember-deep border-ember/50',
      outlined: 'text-ember-deep border-ember/60',
    },
    royal: {
      filled: 'bg-royal/20 text-royal border-royal/50',
      outlined: 'text-royal border-royal/60',
    },
    gold: {
      filled: 'bg-gold-leaf/25 text-ember-deep border-gold-leaf/60',
      outlined: 'text-ember-deep border-gold-leaf/70',
    },
    ink: {
      filled: 'bg-ink-page-shadow/50 text-ink-secondary border-ink-page-shadow',
      outlined: 'text-ink-secondary border-ink-page-shadow',
    },
    rose: {
      filled: 'bg-rose/20 text-ember-deep border-rose/50',
      outlined: 'text-ember-deep border-rose/60',
    },
  };

  const sizes = {
    sm: 'text-[11px] px-2 py-0.5 gap-1',
    md: 'text-xs px-2.5 py-1 gap-1.5',
  };

  const toneClass = (tones[tone] || tones.teal)[variant] || tones.teal.filled;
  const sizeClass = sizes[size] || sizes.sm;

  return (
    <span
      className={`inline-flex items-center rounded-full border font-script font-semibold uppercase tracking-wide ${toneClass} ${sizeClass} ${className}`}
    >
      {icon ? <span className="flex-shrink-0">{icon}</span> : null}
      {children}
    </span>
  );
}
