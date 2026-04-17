import runeOrbUrl from '../../assets/glyphs/rune-orb.svg';

/**
 * RuneBand — shimmering sheikah-teal band displayed across the top of a page
 * while the user is clocked in. Acts as an ever-present reminder that time
 * is being logged without hogging real estate.
 */
export default function RuneBand({ projectTitle, elapsedLabel, onClick }) {
  const Component = onClick ? 'button' : 'div';
  return (
    <Component
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className="relative w-full overflow-hidden rounded-xl border border-sheikah-teal/40 bg-sheikah-teal/10 px-4 py-2.5 text-left hover:bg-sheikah-teal/15 transition-colors block"
    >
      {/* Shimmer layer */}
      <div
        className="pointer-events-none absolute inset-0 animate-rune-band"
        style={{
          background:
            'linear-gradient(90deg, transparent 0%, transparent 40%, rgba(77,208,225,0.28) 50%, transparent 60%, transparent 100%)',
          backgroundSize: '220% 100%',
        }}
      />
      {/* Dotted rune-trace border */}
      <div
        className="pointer-events-none absolute inset-0 rounded-xl"
        style={{
          backgroundImage:
            'repeating-linear-gradient(90deg, var(--color-sheikah-teal) 0 4px, transparent 4px 12px)',
          backgroundSize: '100% 1px',
          backgroundRepeat: 'no-repeat',
          backgroundPosition: '0 0, 0 100%',
          opacity: 0.4,
        }}
      />

      <div className="relative flex items-center gap-3">
        <img
          src={runeOrbUrl}
          alt=""
          aria-hidden="true"
          className="w-6 h-6 text-sheikah-teal-deep animate-rune-pulse"
        />
        <div className="min-w-0 flex-1">
          <div className="font-script text-tiny uppercase tracking-widest text-sheikah-teal-deep">
            Now inking
          </div>
          <div className="font-display text-sm truncate text-ink-primary">
            {projectTitle || 'Unclaimed venture'}
          </div>
        </div>
        <div className="flex-shrink-0 font-rune text-base font-bold text-ink-primary">
          {elapsedLabel}
        </div>
      </div>
    </Component>
  );
}
