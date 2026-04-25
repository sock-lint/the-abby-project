export default function LorebookTile({ entry, onSelect }) {
  const unlocked = !!entry.unlocked;
  const shellBase =
    'relative rounded-2xl p-3 flex flex-col items-center gap-1.5 min-h-[142px] transition-transform';
  const unlockedShell =
    'bg-ink-page-rune-glow/95 border border-ink-page-shadow hover:shadow-lg active:scale-[0.98]';
  const lockedShell =
    'border border-dashed border-ink-whisper/30 bg-ink-page-aged/40 text-ink-whisper/60 shadow-[inset_0_2px_6px_-2px_rgba(45,31,21,0.25),inset_0_-1px_0_rgba(255,248,224,0.4)]';

  const body = (
    <div
      data-lorebook-tile="true"
      data-unlocked={unlocked ? 'true' : 'false'}
      className={`${shellBase} ${unlocked ? unlockedShell : lockedShell}`}
    >
      <div
        className={`relative w-14 h-14 rounded-full flex items-center justify-center ${
          unlocked
            ? 'bg-ink-page-aged shadow-[inset_0_1px_0_rgba(255,248,224,0.6),inset_0_-2px_4px_rgba(45,31,21,0.15)]'
            : 'bg-ink-page-shadow/25 shadow-[inset_0_2px_4px_rgba(45,31,21,0.35),inset_0_-1px_0_rgba(255,248,224,0.25)]'
        }`}
      >
        <span
          aria-hidden="true"
          className={`text-3xl leading-none ${unlocked ? '' : 'grayscale opacity-45'}`}
        >
          {entry.icon || '📖'}
        </span>
      </div>

      <div
        className={`text-caption text-center font-medium leading-tight line-clamp-2 ${
          unlocked ? 'text-ink-primary' : 'text-ink-whisper/75'
        }`}
      >
        {entry.title}
      </div>

      <div
        className={`text-micro font-rune uppercase tracking-wider ${
          unlocked ? 'text-sheikah-teal-deep' : 'text-ink-whisper/55'
        }`}
      >
        {unlocked ? 'discovered' : 'undiscovered'}
      </div>

      <div
        className={`mt-0.5 text-micro italic font-script text-center leading-snug px-1 line-clamp-2 ${
          unlocked ? 'text-ink-whisper' : 'text-ink-whisper/80'
        }`}
      >
        {unlocked ? entry.summary : 'not yet discovered'}
      </div>
    </div>
  );

  if (!unlocked) {
    return (
      <div
        aria-label={`${entry.title} · not yet discovered`}
        role="img"
        className="w-full"
      >
        {body}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onSelect?.(entry)}
      aria-label={`${entry.title} · discovered`}
      className="w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal rounded-2xl"
    >
      {body}
    </button>
  );
}
