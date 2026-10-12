import { useNavigate } from 'react-router-dom';
import { Flame } from 'lucide-react';
import { CoinIcon, EggIcon } from '../icons/JournalIcons';
import RpgSprite from '../rpg/RpgSprite';
import { petSpriteKeys } from '../rpg/petSpriteKeys';

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
      className="min-w-0 flex flex-col items-center justify-center gap-1 rounded-2xl border border-ink-page-shadow bg-ink-page-aged min-h-[72px] px-2 py-2 hover:bg-ink-page-rune-glow transition-colors"
    >
      <div className={`flex min-w-0 max-w-full flex-col items-center gap-1 sm:flex-row ${toneText}`}>
        {icon}
        <span className="max-w-full break-words [overflow-wrap:anywhere] font-rune text-body sm:text-base font-semibold tabular-nums">
          {value}
        </span>
      </div>
      <div className="font-body font-semibold text-tiny text-ink-secondary leading-snug">
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

  const petIcon = activePet ? (
    <RpgSprite
      {...petSpriteKeys(activePet)}
      icon={activePet.species?.icon || '🐾'}
      potionSlug={activePet.potion?.slug}
      dim={activePet.evolved_to_mount || activePet.happiness_level === 'happy' ? null : activePet.happiness_level}
      alt={[activePet.potion?.name, activePet.species?.name || 'Companion'].filter(Boolean).join(' ')}
      size={24}
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
        label={activePet ? 'companion' : 'no pet'}
        tone="royal"
        ariaLabel={activePet ? `${activePet.species?.name || 'pet'} growth` : 'Find a pet'}
        onClick={() => navigate(activePet ? '/bestiary?tab=companions' : '/treasury?tab=satchel')}
      />
    </div>
  );
}
