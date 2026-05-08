import { useEffect, useState } from 'react';
import { Zap, Coins, Gift, Sprout } from 'lucide-react';

/**
 * BoostStrip — compact pill row showing every active consumable boost on
 * a CharacterProfile, with a live countdown. Renders nothing when no
 * boosts are active so it doesn't take up layout space.
 *
 * The serializer surfaces three timer fields in seconds-remaining
 * (`xp_boost_seconds_remaining`, etc., null when inactive) plus
 * `pet_growth_boost_remaining` as a count (number of doubled feeds left).
 * The hook re-renders every second so the countdowns tick visually.
 */
export default function BoostStrip({ profile, className = '' }) {
  const xpInitial = profile?.xp_boost_seconds_remaining ?? null;
  const coinInitial = profile?.coin_boost_seconds_remaining ?? null;
  const dropInitial = profile?.drop_boost_seconds_remaining ?? null;
  const growthCount = profile?.pet_growth_boost_remaining ?? 0;

  // Local tick state — decrement once per second from whatever the server
  // last reported. Resets when `profile` reference changes (after a
  // successful useItem refetch).
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (xpInitial == null && coinInitial == null && dropInitial == null) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [xpInitial, coinInitial, dropInitial]);

  // Anchor: when the component mounts (or `profile` changes), record the
  // wall clock so we can compute remaining = initial - elapsed.
  const [anchorMs] = useState(() => Date.now());
  const elapsedSec = Math.max(0, Math.floor((now - anchorMs) / 1000));
  const xpRemaining = xpInitial != null ? Math.max(0, xpInitial - elapsedSec) : null;
  const coinRemaining = coinInitial != null ? Math.max(0, coinInitial - elapsedSec) : null;
  const dropRemaining = dropInitial != null ? Math.max(0, dropInitial - elapsedSec) : null;

  const chips = [];
  if (xpRemaining && xpRemaining > 0) {
    chips.push({
      key: 'xp',
      icon: <Zap size={12} aria-hidden="true" />,
      label: 'XP boost',
      value: formatDuration(xpRemaining),
      tone: 'gold',
    });
  }
  if (coinRemaining && coinRemaining > 0) {
    chips.push({
      key: 'coin',
      icon: <Coins size={12} aria-hidden="true" />,
      label: 'Coin boost',
      value: formatDuration(coinRemaining),
      tone: 'gold',
    });
  }
  if (dropRemaining && dropRemaining > 0) {
    chips.push({
      key: 'drop',
      icon: <Gift size={12} aria-hidden="true" />,
      label: 'Drop boost',
      value: formatDuration(dropRemaining),
      tone: 'teal',
    });
  }
  if (growthCount > 0) {
    chips.push({
      key: 'growth',
      icon: <Sprout size={12} aria-hidden="true" />,
      label: 'Pet growth',
      value: `× ${growthCount}`,
      tone: 'moss',
    });
  }

  if (chips.length === 0) return null;

  return (
    <div
      role="status"
      aria-label={`${chips.length} active boon${chips.length === 1 ? '' : 's'}`}
      className={`flex flex-wrap items-center gap-2 ${className}`}
    >
      <span className="font-script text-sheikah-teal-deep text-tiny uppercase tracking-wider">
        active boons ·
      </span>
      {chips.map((chip) => (
        <span
          key={chip.key}
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-tiny font-medium ${TONE_CLASSES[chip.tone]}`}
        >
          {chip.icon}
          <span>{chip.label}</span>
          <span className="tabular-nums opacity-80">{chip.value}</span>
        </span>
      ))}
    </div>
  );
}

const TONE_CLASSES = {
  gold: 'bg-gold-leaf/15 text-gold-leaf border border-gold-leaf/30',
  teal: 'bg-sheikah-teal-deep/15 text-sheikah-teal-deep border border-sheikah-teal-deep/30',
  moss: 'bg-moss/15 text-moss-deep border border-moss/30',
};

function formatDuration(seconds) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return s ? `${m}m${s.toString().padStart(2, '0')}s` : `${m}m`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m ? `${h}h${m.toString().padStart(2, '0')}m` : `${h}h`;
}
