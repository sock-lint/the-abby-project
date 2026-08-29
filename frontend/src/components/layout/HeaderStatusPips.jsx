import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, DollarSign, Flame, Stamp } from 'lucide-react';
import { getDashboard } from '../../api';
import { useApi } from '../../hooks/useApi';
import { usePulse } from '../../providers/pulseContext';
import useParentPendingCounts from '../../hooks/useParentPendingCounts';
import { CoinIcon } from '../icons/JournalIcons';
import { formatDuration } from '../../utils/format';

function Pip({ icon, label, tone = 'ink', active = false, onClick, ariaLabel }) {
  const toneClasses = {
    ink: 'text-ink-secondary bg-ink-page-aged border-ink-page-shadow hover:bg-ink-page-rune-glow',
    ember: 'text-ember-deep bg-ember/10 border-ember/40 hover:bg-ember/20',
    gold: 'text-gold-leaf bg-ink-page-aged border-gold-leaf/40 hover:bg-ink-page-rune-glow',
    teal: 'text-sheikah-teal-deep bg-sheikah-teal/10 border-sheikah-teal/50 hover:bg-sheikah-teal/20',
    moss: 'text-moss bg-moss/10 border-moss/40 hover:bg-moss/20',
  }[tone] || 'text-ink-secondary bg-ink-page-aged border-ink-page-shadow';

  // Bump the pip whenever its label changes. Comparing the previous label
  // during render is React's documented way to adjust state on a prop change
  // (https://react.dev/learn/you-might-not-need-an-effect); doing it in an
  // effect meant a synchronous setState there, i.e. a second render pass for
  // every label change. The effect now owns only the timer, so its setState
  // fires from a callback rather than from the effect body.
  const [prevLabel, setPrevLabel] = useState(label);
  const [bumped, setBumped] = useState(false);

  if (prevLabel !== label) {
    setPrevLabel(label);
    if (prevLabel !== undefined) setBumped(true);
  }

  useEffect(() => {
    if (!bumped) return undefined;
    const timer = setTimeout(() => setBumped(false), 600);
    return () => clearTimeout(timer);
  }, [bumped]);

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel || label}
      className={`inline-flex items-center gap-1.5 h-11 px-3 rounded-full border text-caption font-rune tabular-nums transition-all ${toneClasses} ${active ? 'animate-rune-pulse' : ''} ${bumped ? 'scale-110 ring-2 ring-sheikah-teal/40' : ''}`}
    >
      <span className="shrink-0 flex items-center">{icon}</span>
      <span className="leading-none">{label}</span>
    </button>
  );
}

/**
 * HeaderStatusPips — role-aware 2-3 pip strip for the global header.
 *   Child:  streak · coins · (clock if running)
 *   Parent: pending-approvals · week-earnings · (clock if any kid running)
 * The clock pip takes priority whenever active.
 */
export default function HeaderStatusPips({ user }) {
  const navigate = useNavigate();
  // Caller passes ``user`` so we still respect the prop API. Use the
  // shared role check to keep the convention consistent.
  const isParent = user?.role === 'parent';
  // NOTE: HeaderStatusPips is mounted inside JournalShell which receives
  // ``user`` as a prop, so it doesn't read from useRole(). When the
  // shell is migrated to context-only, this can drop the prop and use
  // ``useRole().isParent`` directly.

  const { data: dashboard } = useApi(getDashboard);
  // The dashboard is fetched once at shell mount and the shell never
  // remounts, so these numbers used to sit frozen all day — a kid could
  // finish three chores, watch the drop toasts fire, and still see the
  // morning's coin count. The heartbeat carries fresh values; fall back to
  // the mount-time payload until the first beat lands.
  const { pulse } = usePulse();

  // Parent-only pending counts. Shared with ``useParentDashboard`` via the
  // ``useParentPendingCounts`` hook so the two callers don't fork the
  // Promise.all of the same three endpoints.
  const { total: pending } = useParentPendingCounts({ enabled: isParent });

  const activeTimer = pulse?.header?.active_timer ?? dashboard?.active_timer ?? null;
  const coins = pulse?.header?.coin_balance ?? dashboard?.coin_balance ?? 0;
  const streak = pulse?.header?.streak_days
    ?? dashboard?.rpg?.login_streak ?? dashboard?.streak_days ?? 0;
  const weekEarnings = dashboard?.this_week?.earnings ?? 0;

  const pips = useMemo(() => {
    const out = [];
    if (activeTimer) {
      out.push({
        key: 'clock',
        icon: <Clock size={14} />,
        // Same formatter as the hero card's live timer — the pip used to
        // hand-roll "1h 05", which reads as a clock time, not a duration.
        label: formatDuration(activeTimer.elapsed_minutes),
        tone: 'teal',
        active: true,
        ariaLabel: `Clocked in on ${activeTimer.project_title}`,
        onClick: () => navigate('/clock'),
      });
    }
    if (isParent) {
      out.push({
        key: 'approvals',
        icon: <Stamp size={14} />,
        label: String(pending),
        tone: pending > 0 ? 'ember' : 'ink',
        ariaLabel: `${pending} pending approvals`,
        onClick: () => {
          // Best-effort in-page anchor; falls back to dashboard.
          const el = typeof document !== 'undefined'
            ? document.getElementById('approval-queue')
            : null;
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
          else navigate('/');
        },
      });
      out.push({
        key: 'earnings',
        // DollarSign, not CoinIcon: this pip is money. CoinIcon means the
        // coins currency everywhere else in the app and the two economies
        // are deliberately separate.
        icon: <DollarSign size={14} />,
        label: `$${Math.round(Number(weekEarnings) || 0)}`,
        tone: 'gold',
        ariaLabel: 'Earnings this week',
        onClick: () => navigate('/treasury?tab=wages'),
      });
    } else {
      out.push({
        key: 'streak',
        icon: <Flame size={14} />,
        label: String(streak),
        tone: streak > 0 ? 'ember' : 'ink',
        ariaLabel: `${streak}-day streak`,
        onClick: () => navigate('/sigil'),
      });
      out.push({
        key: 'coins',
        icon: <CoinIcon size={14} />,
        label: String(coins),
        tone: 'gold',
        ariaLabel: `${coins} coins`,
        onClick: () => navigate('/treasury?tab=bazaar'),
      });
    }
    return out;
  }, [activeTimer, isParent, pending, streak, coins, weekEarnings, navigate]);

  return (
    <div className="flex items-center gap-1.5 md:gap-2 min-w-0 overflow-x-auto scrollbar-hide">
      {pips.map((p) => (
        <Pip
          key={p.key}
          icon={p.icon}
          label={p.label}
          tone={p.tone}
          active={p.active}
          onClick={p.onClick}
          ariaLabel={p.ariaLabel}
        />
      ))}
    </div>
  );
}
