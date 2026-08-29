import { useEffect, useState } from 'react';
import { getPrinterStatus } from '../../api';
import FilamentChip from './FilamentChip';

/**
 * FilamentPicker — tap what's actually loaded instead of typing a colour.
 *
 * Three things about this are deliberate, and each is a way the obvious
 * version would be wrong:
 *
 * **It fills the field in; it does not replace it.** The AMS reports what is
 * loaded *right now*. A request submitted on Tuesday might print on Saturday
 * with entirely different spools in the bays, so this is a convenience, never
 * a constraint — the free-text Colour field underneath stays authoritative and
 * always editable. We store the human-readable name, never a slot number,
 * because "A2" means something different next week.
 *
 * **It renders nothing at all when it has nothing to offer.** The snapshot
 * expires five minutes after the listener stops reporting, and children submit
 * requests when the printer is off. A picker that showed "no filament found"
 * would read as a broken feature on the perfectly normal path where the
 * printer is simply asleep; a form that looks exactly like it did before is
 * the right answer.
 *
 * **It fails silently.** This is decoration on a form that has to keep
 * working. A status call that 500s must not put an error above a child's
 * print request.
 */
export default function FilamentPicker({ printers, value, onSelect }) {
  const [filaments, setFilaments] = useState([]);

  const ids = (printers || [])
    .filter((printer) => printer.is_active !== false)
    .map((printer) => printer.id);
  // The dependency is the id list, not the array identity: the parent rebuilds
  // `printers` on every render and an array in the dep list would re-fetch on
  // each keystroke in the form above.
  const key = ids.join(',');

  useEffect(() => {
    let live = true;

    (async () => {
      if (!key) {
        // Every write goes through the async path: a synchronous setState in
        // an effect body cascades a second render before paint.
        if (live) setFilaments([]);
        return;
      }
      const results = await Promise.all(
        key.split(',').map(async (id) => {
          try {
            const data = await getPrinterStatus(id);
            return data?.live?.filaments || [];
          } catch {
            // Decoration on a working form: never surface this.
            return [];
          }
        }),
      );
      if (!live) return;

      // A household with two printers loaded from the same shelf would
      // otherwise show the same spool twice. Dedupe on what the child
      // actually reads — name plus colour — keeping the first slot seen.
      const seen = new Set();
      const merged = [];
      results.flat().forEach((filament) => {
        const identity = `${filament.display_name}|${filament.hex}`;
        if (seen.has(identity)) return;
        seen.add(identity);
        merged.push(filament);
      });
      setFilaments(merged);
    })();

    return () => { live = false; };
  }, [key]);

  if (filaments.length === 0) return null;

  return (
    <div className="space-y-1.5">
      <p className="font-script text-caption text-ink-whisper">
        Loaded right now — tap one, or type your own below.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {filaments.map((filament) => (
          <FilamentChip
            key={`${filament.slot}-${filament.display_name}`}
            filament={filament}
            selected={value === filament.display_name}
            onSelect={() => onSelect(filament.display_name)}
          />
        ))}
      </div>
    </div>
  );
}
