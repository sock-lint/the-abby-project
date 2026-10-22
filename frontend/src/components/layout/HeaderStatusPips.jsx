import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, DollarSign, Stamp } from 'lucide-react';
import { CoinIcon } from '../icons/JournalIcons';
import HeaderStreakFlame from './HeaderStreakFlame';
import { streakBonusStage } from '../../streak/bonusPresentation';
import { getDashboard } from '../../api';
import { useApi } from '../../hooks/useApi';
import { usePulse } from '../../providers/pulseContext';
import useParentPendingCounts from '../../hooks/useParentPendingCounts';
import useScrollFades from '../../hooks/useScrollFades';
import { formatDuration } from '../../utils/format';

function Pip({ icon, label, tone = 'ink', active = false, onClick, ariaLabel, description }) {
  const descriptionId = useId();
  const toneClasses = {
    ink: 'text-ink-secondary bg-ink-page-aged border-ink-page-shadow/60 hover:bg-ink-page',
    ember: 'text-ember-deep bg-ember/10 border-ember/25 hover:bg-ember/15',
    gold: 'text-gold-leaf bg-gold-leaf/10 border-gold-leaf/25 hover:bg-gold-leaf/15',
    teal: 'text-sheikah-teal-deep bg-sheikah-teal/10 border-sheikah-teal/25 hover:bg-sheikah-teal/15',
    moss: 'text-moss bg-moss/10 border-moss/25 hover:bg-moss/15',
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
      aria-describedby={description ? descriptionId : undefined}
      title={description}
      className={`inline-flex shrink-0 items-center gap-1.5 min-w-11 h-11 px-3 rounded-2xl border text-caption font-body font-bold tabular-nums transition-colors ${toneClasses} ${active || bumped ? 'ring-2 ring-inset ring-sheikah-teal/25' : ''}`}
    >
      <span className="shrink-0 flex items-center">{icon}</span>
      <span className="leading-none text-ink-primary">{label}</span>
      {description && <span id={descriptionId} className="sr-only">{description}</span>}
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
  const stripRef = useRef(null);
  const { showLeft, showRight, onScroll } = useScrollFades(stripRef);
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
  const { total: pending, ready: attentionReady, incomplete: attentionIncomplete } = useParentPendingCounts({ enabled: isParent });

  const activeTimer = pulse?.header?.active_timer ?? dashboard?.active_timer ?? null;
  const coins = pulse?.header?.coin_balance ?? dashboard?.coin_balance ?? 0;
  const streak = pulse?.header?.streak_days
    ?? dashboard?.rpg?.login_streak ?? dashboard?.streak_days ?? 0;
  // Once a heartbeat arrives, its bonus is authoritative, including false,
  // zero, or missing during a rolling deploy. Never revive a stale mount bonus.
  const streakBonus = pulse?.header ? pulse.header.streak_bonus : dashboard?.rpg?.streak_bonus;
  const streakStage = streakBonusStage(streakBonus);
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
        label: !attentionReady ? '…' : attentionIncomplete ? `${pending || '?'}${pending ? '+' : ''}` : String(pending),
        tone: pending > 0 ? 'ember' : 'ink',
        ariaLabel: !attentionReady ? 'Checking items needing attention' : attentionIncomplete ? 'Some review queues are unavailable' : `${pending} items needing attention`,
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
        icon: <HeaderStreakFlame stage={streakStage} />,
        label: String(streak),
        tone: streakStage !== 'unknown' && streakBonus.active_today ? 'ember' : 'ink',
        ariaLabel: `${streak}-day streak`,
        description: streakStage === 'unknown' ? 'Streak bonus is unavailable.'
          : streakBonus.active_today
            ? `Daily check-in: ${streakBonus.check_in_coins} Coins at ${streakBonus.check_in_multiplier}×. Streak drop chance: +${Math.round(streakBonus.drop_bonus * 100)} percentage points.`
            : 'Streak bonus is inactive. Complete an activity to start today’s check-in.',
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
  }, [activeTimer, isParent, pending, attentionReady, attentionIncomplete, streak, streakBonus, streakStage, coins, weekEarnings, navigate]);

  // A larger count can change scrollWidth without resizing the rail itself.
  // Refresh the cues after each new set of labels as well as on scroll/resize.
  useEffect(() => { onScroll(); }, [onScroll, pips]);

  const revealFocusedPip = (event) => {
    const strip = stripRef.current;
    if (!strip) return;
    const rail = strip.getBoundingClientRect();
    const pip = event.target.getBoundingClientRect();
    const delta = pip.left < rail.left ? pip.left - rail.left
      : pip.right > rail.right ? pip.right - rail.right : 0;
    // Browser focus scrolling can leave a partially visible button clipped.
    // Reveal it within this rail without scrolling the page or moving focus.
    // Bounds include CSS zoom; scrollLeft is in unscaled layout pixels.
    const scale = strip.clientWidth ? rail.width / strip.clientWidth : 1;
    if (delta) strip.scrollTo?.({ left: Math.max(0, strip.scrollLeft + delta / scale), behavior: 'auto' });
    onScroll();
  };

  return (
    <div role="group" aria-label="Status shortcuts" className="relative min-w-0 max-w-full">
      {showLeft && (
        <div
          aria-hidden="true"
          data-scroll-fade="left"
          className="pointer-events-none absolute inset-y-0 left-0 w-4 z-10 bg-gradient-to-r from-ink-page to-transparent"
        />
      )}
      {showRight && (
        <div
          aria-hidden="true"
          data-scroll-fade="right"
          className="pointer-events-none absolute inset-y-0 right-0 w-4 z-10 bg-gradient-to-l from-ink-page to-transparent"
        />
      )}
      <div ref={stripRef} onScroll={onScroll} onFocus={revealFocusedPip} className="flex items-center gap-1.5 md:gap-2 min-w-0 overflow-x-auto scrollbar-hide">
        {pips.map((p) => (
          <Pip
            key={p.key}
            icon={p.icon}
            label={p.label}
            tone={p.tone}
            active={p.active}
            onClick={p.onClick}
            ariaLabel={p.ariaLabel}
            description={p.description}
          />
        ))}
      </div>
    </div>
  );
}
