import { Check, Flame, Sparkles } from 'lucide-react';
import { CoinIcon } from '../../components/icons/JournalIcons';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import ProgressBar from '../../components/ProgressBar';

export default function ReadingAdventure({ adventure }) {
  if (!adventure) return null;
  return <ParchmentCard as="section" aria-label="Today’s reading reward" className="!p-4 space-y-3">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-moss-deep" aria-hidden="true" /><h3 className="font-bold text-ink-primary">Today’s reading reward</h3></div>
      <RuneBadge tone={adventure.earned ? 'moss' : 'teal'}>{adventure.earned ? 'Earned today' : `${adventure.minutes_credited} / ${adventure.target_minutes} minutes`}</RuneBadge>
    </div>
    <ProgressBar value={adventure.minutes_credited} max={adventure.target_minutes} aria-label="Today’s reading reward minutes" />
    {adventure.earned ? <p className="flex items-start gap-2 text-body font-semibold text-moss-deep"><Check className="h-5 w-5 shrink-0" aria-hidden="true" /><span>Earned today: {adventure.xp_awarded} {adventure.skill_name} XP and {adventure.coins_awarded} Coins.</span></p> : <>
      <p className="text-body text-ink-primary">Read or listen for {adventure.remaining_minutes} more {adventure.remaining_minutes === 1 ? 'minute' : 'minutes'} today to earn your daily reward. Short sessions add up.</p>
      <div className="flex flex-wrap gap-3 text-caption font-semibold text-ink-primary">
        <span className="inline-flex items-center gap-1"><Sparkles className="h-4 w-4 text-moss-deep" aria-hidden="true" />{adventure.base_xp} base {adventure.skill_name} XP</span>
        <span className="inline-flex items-center gap-1"><CoinIcon size={16} aria-hidden="true" />{adventure.base_coins} base Coins</span>
      </div>
    </>}
    <p className="flex items-start gap-2 text-caption text-ink-secondary"><Flame className="h-4 w-4 shrink-0 text-ember-deep" aria-hidden="true" /><span>{adventure.earned ? 'Your daily reading reward is complete. More reading is always welcome; another reward is available tomorrow.' : `Reaching ${adventure.target_minutes} minutes also counts toward your activity streak and gives a chance of loot. Active boosts can increase XP and Coins.`}</span></p>
    <p className="text-caption text-ink-secondary">Only new logs dated today count toward this reward. Audiobooks count, and reading notes are always optional.</p>
  </ParchmentCard>;
}
