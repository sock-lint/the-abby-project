import { useNavigate } from 'react-router-dom';
import { Flame } from 'lucide-react';
import { CoinIcon, EggIcon } from '../icons/JournalIcons';

function VitalPip({ label, value, icon, tone = 'ink', onClick, ariaLabel }) {
  const toneText = {
    gold: 'text-gold-leaf',
    ember: 'text-ember-deep',
    teal: 'text-sheikah-teal-deep',
    moss: 'text-moss',
    royal: 'text-royal',
    ink: 'text-ink-secondary',
  }[tone] || 'text-ink-secondary';

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel || `${label}: ${value}`}
      className="flex flex-col items-center justify-center gap-0.5 rounded-xl border border-ink-page-shadow bg-ink-page-aged min-h-[72px] px-2 py-2 hover:bg-ink-page-rune-glow transition-colors"
    >
      <div className={`flex items-center gap-1 ${toneText}`}>
        {icon}
        <span className="font-rune text-base font-semibold tabular-nums">
          {value}
        </span>
      </div>
      <div className="font-script text-tiny text-ink-whisper uppercase tracking-wider leading-none">
        {label}
      </div>
    </button>
  );
}

/**
 * VitalPipStrip — horizontal 4-pip row replacing the old stacked vital cards.
 * Pips: coins, streak, level, pet thumb. Tap each to drill in.
 */
export default function VitalPipStrip({
  coinBalance = 0,
  loginStreak = 0,
  level = 1,
  activePet = null,
}) {
  const navigate = useNavigate();

  const petIcon = activePet?.species?.icon_url ? (
    <img
      src={activePet.species.icon_url}
      alt=""
      className="w-5 h-5 object-contain"
      aria-hidden="true"
    />
  ) : (
    <EggIcon size={16} />
  );

  return (
    <div className="grid grid-cols-4 gap-2">
      <VitalPip
        icon={<CoinIcon size={16} />}
        value={coinBalance ?? 0}
        label="coins"
        tone="gold"
        ariaLabel={`${coinBalance ?? 0} coins`}
        onClick={() => navigate('/treasury?tab=bazaar')}
      />
      <VitalPip
        icon={<Flame size={16} />}
        value={loginStreak ?? 0}
        label="streak"
        tone={loginStreak > 0 ? 'ember' : 'ink'}
        ariaLabel={`${loginStreak}-day streak`}
        onClick={() => navigate('/sigil')}
      />
      <VitalPip
        value={`L${level ?? 1}`}
        label="level"
        tone="teal"
        icon={null}
        ariaLabel={`Level ${level}`}
        onClick={() => navigate('/sigil')}
      />
      <VitalPip
        icon={petIcon}
        value={activePet ? (activePet.growth_points != null ? `${activePet.growth_points}%` : '•') : '—'}
        label={activePet ? 'pet' : 'no pet'}
        tone="royal"
        ariaLabel={activePet ? `${activePet.species?.name || 'pet'} growth` : 'Find a pet'}
        onClick={() => navigate(activePet ? '/bestiary?tab=party' : '/bestiary?tab=satchel')}
      />
    </div>
  );
}
