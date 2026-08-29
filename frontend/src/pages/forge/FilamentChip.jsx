/**
 * FilamentChip — one spool as the printer reports it.
 *
 * Rendered in two places with the same shape: read-only on the live printer
 * card, and as a button in the request form's picker. Both need to be honest
 * about what the AMS does *not* know, which is most of what makes this
 * component more than a coloured dot:
 *
 * - `hex` is null for a bay whose tag was never read. A null swatch renders
 *   as a dashed outline, not as black — `#000000` is real black filament and
 *   the two must not look alike.
 * - `remain_percent` is null for any spool without an RFID tag, which is
 *   every third-party roll. We show nothing rather than a zero, because a
 *   "0%" on a full spool is worse than no number at all.
 *
 * The swatch is decorative; the slot and name carry the meaning, so screen
 * readers get the colour only through the accessible label.
 */
import { describeFilament } from './forge.constants';

function Swatch({ hex }) {
  return (
    <span
      aria-hidden="true"
      data-swatch={hex ? 'known' : 'unknown'}
      className={[
        'h-3.5 w-3.5 shrink-0 rounded-full border',
        hex ? 'border-ink-page-shadow/50' : 'border-dashed border-ink-whisper',
      ].join(' ')}
      style={hex ? { backgroundColor: hex } : undefined}
    />
  );
}

export default function FilamentChip({ filament, selected = false, onSelect }) {
  const label = describeFilament(filament);
  const body = (
    <>
      <Swatch hex={filament.hex} />
      <span className="font-script text-caption text-ink-whisper shrink-0">
        {filament.slot}
      </span>
      <span className="font-body text-caption text-ink-secondary truncate">
        {filament.display_name || filament.material}
      </span>
      {typeof filament.remain_percent === 'number' && (
        <span className="font-script text-caption text-ink-whisper shrink-0">
          {filament.remain_percent}%
        </span>
      )}
    </>
  );

  const shared = 'flex items-center gap-1.5 rounded-full border px-2.5 py-1 max-w-full';

  if (!onSelect) {
    return (
      <span
        data-filament={filament.slot}
        title={label}
        aria-label={label}
        className={`${shared} border-ink-page-shadow/40 bg-page-aged/40`}
      >
        {body}
      </span>
    );
  }

  return (
    <button
      type="button"
      data-filament={filament.slot}
      aria-pressed={selected}
      title={label}
      aria-label={label}
      onClick={() => onSelect(filament)}
      className={[
        shared,
        'transition-colors',
        selected
          ? 'border-sheikah-teal-deep bg-sheikah-teal-deep/10'
          : 'border-ink-page-shadow/40 hover:border-sheikah-teal-deep/60',
      ].join(' ')}
    >
      {body}
    </button>
  );
}
