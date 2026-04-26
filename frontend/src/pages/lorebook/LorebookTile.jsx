export default function LorebookTile({ entry, onSelect }) {
  const unlocked = !!entry.unlocked;
  const trained = !!entry.trained;
  const shellBase =
    'relative rounded-2xl p-3 flex flex-col items-center gap-1.5 min-h-[142px] transition-transform';
  const trainedShell =
    'bg-ink-page-rune-glow/95 border border-ink-page-shadow hover:shadow-lg active:scale-[0.98]';
  const encounteredShell =
    'bg-ink-page-aged border border-sheikah-teal-deep/50 shadow-[0_0_0_1px_rgba(0,0,0,0)] hover:border-sheikah-teal-deep hover:shadow-md active:scale-[0.98]';
  const lockedShell =
    'border border-dashed border-ink-whisper/30 bg-ink-page-aged/40 text-ink-whisper/60 shadow-[inset_0_2px_6px_-2px_rgba(45,31,21,0.25),inset_0_-1px_0_rgba(255,248,224,0.4)]';

  let shell;
  let runeLabel;
  let kicker;
  let stateText;
  let mode;

  if (!unlocked) {
    shell = lockedShell;
    runeLabel = 'undiscovered';
    kicker = 'discover by trying it in the app';
    stateText = `${entry.title} · not yet discovered`;
    mode = null;
  } else if (!trained) {
    shell = encounteredShell;
    runeLabel = 'untrained';
    kicker = 'tap to begin training';
    stateText = `${entry.title} · ready to train`;
    mode = 'trial';
  } else {
    shell = trainedShell;
    runeLabel = 'inked';
    kicker = entry.summary;
    stateText = `${entry.title} · inked`;
    mode = 'detail';
  }

  const body = (
    <div
      data-lorebook-tile="true"
      data-unlocked={unlocked ? 'true' : 'false'}
      data-trained={trained ? 'true' : 'false'}
      className={`${shellBase} ${shell}`}
    >
      {unlocked && !trained && (
        <span
          aria-hidden="true"
          className="absolute top-1.5 right-1.5 inline-flex items-center rounded-full bg-sheikah-teal-deep px-2 py-0.5 text-micro font-rune uppercase tracking-wider text-ink-page"
        >
          train
        </span>
      )}
      {unlocked && trained && (
        <span
          aria-hidden="true"
          className="absolute top-1.5 right-1.5 text-base leading-none"
          title="Inked"
        >
          🪶
        </span>
      )}

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
        {runeLabel}
      </div>

      <div
        className={`mt-0.5 text-micro italic font-script text-center leading-snug px-1 line-clamp-2 ${
          unlocked ? 'text-ink-whisper' : 'text-ink-whisper/80'
        }`}
      >
        {kicker}
      </div>
    </div>
  );

  if (!mode) {
    return (
      <div aria-label={stateText} role="img" className="w-full">
        {body}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onSelect?.(entry, mode)}
      aria-label={stateText}
      className="w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal rounded-2xl"
    >
      {body}
    </button>
  );
}
