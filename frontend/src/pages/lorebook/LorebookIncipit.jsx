import ParchmentCard from '../../components/journal/ParchmentCard';
import IlluminatedVersal from '../achievements/IlluminatedVersal';
import { tierForProgress } from '../achievements/mastery.constants';

export default function LorebookIncipit({ unlocked, trained = 0, total, mode = 'kid' }) {
  // Progression bar tracks inked-page progress (the new training goal). The
  // discovery count stays visible as a quieter line so the auto-element of
  // unlocking-by-real-action remains legible.
  const progressPct = total ? (trained / total) * 100 : 0;
  const tier = tierForProgress({ unlocked: total > 0, progressPct, level: 0 });

  return (
    <ParchmentCard variant="sealed" tone="bright" flourish seal="top-right" className="overflow-hidden">
      <div className="flex items-center gap-5 pr-12">
        <IlluminatedVersal
          letter="L"
          size="xl"
          tier={tier}
          progressPct={progressPct}
        />
        <div className="flex-1 min-w-0">
          <div className="font-script text-sheikah-teal-deep text-base leading-snug">
            · the lorebook of mechanics ·
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Lorebook
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-caption font-script text-ink-whisper">
            {mode === 'parent' ? (
              <span>
                <span className="tabular-nums">{total || 0}</span> entries visible
              </span>
            ) : (
              <>
                <span>
                  <span className="tabular-nums">{trained}</span> of {total || 0} inked
                </span>
                <span aria-hidden="true" className="text-ink-whisper/40">·</span>
                <span className="text-micro text-ink-whisper/80">
                  <span className="tabular-nums">{unlocked}</span> discovered
                </span>
              </>
            )}
          </div>
        </div>
      </div>
      <p className="mt-4 text-sm text-ink-secondary max-w-3xl">
        {mode === 'parent'
          ? 'A keeper-facing guide to what pays money, Coins, XP, drops, quest progress, and streak credit.'
          : 'A field guide to the hidden rules of Abby. Each page unlocks when you first meet it in the real app — then a quick training trial inks it into your lorebook for keeps.'}
      </p>
    </ParchmentCard>
  );
}
