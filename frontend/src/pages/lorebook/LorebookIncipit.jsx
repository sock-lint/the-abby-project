import ParchmentCard from '../../components/journal/ParchmentCard';
import IlluminatedVersal from '../achievements/IlluminatedVersal';
import { tierForProgress } from '../achievements/mastery.constants';

export default function LorebookIncipit({ unlocked, total, mode = 'kid' }) {
  const progressPct = total ? (unlocked / total) * 100 : 0;
  const tier = tierForProgress({ unlocked: total > 0, progressPct, level: 0 });
  const noun = mode === 'parent' ? 'entries visible' : 'discovered';

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
          <div className="mt-1 inline-flex items-center gap-2 text-caption font-script text-ink-whisper">
            <span className="tabular-nums">
              §I of {total || 0}
            </span>
            <span>
              {unlocked} of {total || 0} {noun}
            </span>
          </div>
        </div>
      </div>
      <p className="mt-4 text-sm text-ink-secondary max-w-3xl">
        {mode === 'parent'
          ? 'A keeper-facing guide to what pays money, Coins, XP, drops, quest progress, and streak credit.'
          : 'A field guide to the hidden rules of Abby — each page lights up when you first meet that part of the adventure.'}
      </p>
    </ParchmentCard>
  );
}
