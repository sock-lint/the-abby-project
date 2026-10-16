import { useEffect, useState } from 'react';
import { Zap, Gift, Sprout } from 'lucide-react';
import { CoinIcon } from '../icons/JournalIcons';

/**
 * BoostStrip — compact pill row showing every active consumable boost on
 * a CharacterProfile, with a live countdown. Renders nothing when no
 * boosts are active so it doesn't take up layout space.
 *
 * Absolute expiry fields govern the timer when available. Compatibility
 * seconds-remaining values count down from receipt of that profile, while
 * `pet_growth_boost_remaining` counts the doubled feeds left.
 */
export default function BoostStrip({ profile, className = '' }) {
  const [receipt, setReceipt] = useState({ profile, generation: 0 });
  if (profile !== receipt.profile) {
    // A refetch supplies a new profile snapshot. Remount its countdown to
    // capture a fresh clock in the state initializer, without an effect
    // resetting state after a stale duration has already been painted.
    setReceipt({ profile, generation: receipt.generation + 1 });
  }
  return <BoostCountdown key={receipt.generation} profile={profile} className={className} />;
}

function BoostCountdown({ profile, className }) {
  const [anchorMs] = useState(() => Date.now());
  const [now, setNow] = useState(anchorMs);
  const xpRemaining = remainingSeconds(profile, 'xp', now, anchorMs);
  const coinRemaining = remainingSeconds(profile, 'coin', now, anchorMs);
  const dropRemaining = remainingSeconds(profile, 'drop', now, anchorMs);
  const growthCount = profile?.pet_growth_boost_remaining ?? 0;
  const hasCountdown = [xpRemaining, coinRemaining, dropRemaining].some((remaining) => remaining > 0);
  useEffect(() => {
    if (!hasCountdown) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [hasCountdown]);

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
      icon: <CoinIcon size={12} aria-hidden="true" />,
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

function remainingSeconds(profile, kind, now, anchorMs) {
  const expiresAt = Date.parse(profile?.[`${kind}_boost_expires_at`]);
  if (Number.isFinite(expiresAt)) return Math.max(0, Math.ceil((expiresAt - now) / 1000));
  const initial = profile?.[`${kind}_boost_seconds_remaining`];
  if (initial == null) return null;
  const elapsedSec = Math.max(0, Math.floor((now - anchorMs) / 1000));
  return Math.max(0, initial - elapsedSec);
}

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
