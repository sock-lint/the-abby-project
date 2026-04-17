import ParchmentCard from '../../components/journal/ParchmentCard';
import QuillProgress from '../../components/QuillProgress';
import { countIlluminated } from './mastery.constants';
import { XP_THRESHOLDS } from './skillTree.constants';

/**
 * CategoryCapitulare — the illuminated hero stripe at the top of an active
 * skill tree. "Capitulare" is the medieval term for the ornate leading
 * paragraph of a manuscript chapter; this is the digital equivalent, a brief
 * incipit that answers "where am I and how far along am I" at a glance.
 */
export default function CategoryCapitulare({ tree }) {
  const { category, summary, subjects } = tree;
  const level = summary?.level ?? 0;
  const totalXp = summary?.total_xp ?? 0;
  const next = XP_THRESHOLDS[level + 1] ?? XP_THRESHOLDS[6];
  const current = XP_THRESHOLDS[level] ?? 0;
  const inLevel = Math.max(0, totalXp - current);
  const span = Math.max(1, next - current);
  const pct = Math.min(100, (inLevel / span) * 100);

  const { illuminated, total } = countIlluminated(subjects);
  const toNext = Math.max(0, next - totalXp);
  const maxed = level >= 6;

  return (
    <ParchmentCard tone="bright" flourish className="!p-4 md:!p-5">
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className="text-3xl md:text-4xl leading-none">
          {category.icon || '✦'}
        </span>
        <div className="flex-1 min-w-0">
          <div className="font-script text-sheikah-teal-deep text-caption leading-none">
            the atlas · chapter {category.id}
          </div>
          <h2 className="font-display italic text-lede md:text-2xl leading-tight text-ink-primary truncate">
            {category.name}
          </h2>
        </div>
        <div className="text-right shrink-0">
          <div className="font-display text-xl md:text-2xl font-bold text-ember-deep leading-none">
            L{level}
          </div>
          <div className="text-micro font-rune uppercase tracking-wider text-ink-whisper mt-1">
            {totalXp.toLocaleString()} XP
          </div>
        </div>
      </div>

      <div className="mt-3">
        <QuillProgress
          value={pct}
          color="bg-gold-leaf"
          aria-label={`${category.name} category progress toward level ${level + 1}`}
        />
        <div className="flex items-center justify-between text-caption text-ink-whisper mt-1.5">
          <span className="font-script">
            {illuminated} of {total} skills illuminated
          </span>
          <span className="font-rune text-micro uppercase tracking-wider">
            {maxed ? 'mastery sealed' : `${toNext.toLocaleString()} to L${level + 1}`}
          </span>
        </div>
      </div>
    </ParchmentCard>
  );
}
