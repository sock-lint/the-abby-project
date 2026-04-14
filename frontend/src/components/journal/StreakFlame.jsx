/**
 * StreakFlame — animated flame showing the user's current daily streak.
 * Dims and desaturates on missed days (streak === 0).
 *
 * Sits on the Today journal page and surfaces the hidden multiplier for
 * check-in coin bonuses so Abby can feel the streak working.
 */
export default function StreakFlame({
  streak = 0,
  longest = 0,
  multiplier,
  className = '',
}) {
  const alive = streak > 0;
  // Color intensity ramps with streak (pale → ember → gold at 14+, royal at 30+)
  const flameFill = !alive
    ? 'text-ink-whisper'
    : streak >= 30
    ? 'text-royal'
    : streak >= 14
    ? 'text-gold-leaf'
    : streak >= 7
    ? 'text-ember'
    : 'text-ember-deep';

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div className="relative w-14 h-14 flex items-center justify-center">
        <svg
          viewBox="0 0 48 64"
          className={`w-full h-full ${flameFill} ${alive ? 'animate-flame-flicker' : 'opacity-40'}`}
          aria-hidden="true"
        >
          <defs>
            <radialGradient id="flameCore" cx="50%" cy="70%" r="60%">
              <stop offset="0%" stopColor="currentColor" stopOpacity="1" />
              <stop offset="70%" stopColor="currentColor" stopOpacity="0.4" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </radialGradient>
          </defs>
          {/* Outer flame */}
          <path
            d="M24 4 C 14 18, 6 30, 10 44 C 12 54, 18 60, 24 62 C 30 60, 36 54, 38 44 C 42 30, 34 18, 24 4 Z"
            fill="currentColor"
            fillOpacity="0.28"
          />
          {/* Inner flame */}
          <path
            d="M24 14 C 18 24, 14 34, 16 44 C 18 52, 22 56, 24 58 C 26 56, 30 52, 32 44 C 34 34, 30 24, 24 14 Z"
            fill="url(#flameCore)"
          />
          {/* Core ember */}
          <ellipse cx="24" cy="48" rx="4" ry="7" fill="currentColor" fillOpacity="0.9" />
        </svg>
        {/* Streak number overlay */}
        <span
          className={`absolute inset-0 flex items-center justify-center font-rune font-bold text-sm
            ${alive ? 'text-ink-page-rune-glow' : 'text-ink-whisper'}`}
          style={{
            textShadow: alive
              ? '0 0 8px rgba(45,31,21,0.7), 0 1px 2px rgba(45,31,21,0.9)'
              : 'none',
          }}
        >
          {streak}
        </span>
      </div>

      <div className="min-w-0">
        <div className="font-display text-lg leading-tight text-ink-primary">
          {alive ? (streak === 1 ? '1 day' : `${streak} days`) : 'Streak asleep'}
        </div>
        <div className="font-script text-xs text-ink-whisper leading-tight mt-0.5">
          {longest > 0 ? `longest: ${longest}` : 'no streak yet'}
          {multiplier && alive ? ` · ${multiplier}× coins` : ''}
        </div>
      </div>
    </div>
  );
}
