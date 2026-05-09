import { useEffect, useMemo, useState } from 'react';
import { TestTubeDiagonal } from 'lucide-react';
import EmptyState from '../../components/EmptyState';
import Loader from '../../components/Loader';
import { TextField, SelectField, CheckboxField } from '../../components/form';
import {
  devForceCelebration,
  devForceDrop,
  devExpireJournal,
  devResetDayCounters,
  devSetPetHappiness,
  devSetRewardStock,
  devSetStreak,
  devTickPerfectDay,
  devToolsChildren,
  devToolsItems,
  devToolsRewards,
} from '../../api';
import ChecklistRail from './test/ChecklistRail';
import DevToolCard from './test/DevToolCard';

/**
 * TestSection — parent + DEBUG/DEV_TOOLS_ENABLED only.
 *
 * The Manage tab calls /api/dev/ping/ before rendering this section so
 * we never mount when the gate is off. Inside, each card wraps one
 * /api/dev/* endpoint with a tiny inline form.
 */
export default function TestSection() {
  const [children, setChildren] = useState([]);
  const [rewards, setRewards] = useState([]);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [bootError, setBootError] = useState('');

  useEffect(() => {
    let alive = true;
    Promise.allSettled([devToolsChildren(), devToolsRewards(), devToolsItems()])
      .then(([c, r, i]) => {
        if (!alive) return;
        if (c.status === 'fulfilled') setChildren(Array.isArray(c.value) ? c.value : []);
        if (r.status === 'fulfilled') setRewards(Array.isArray(r.value) ? r.value : []);
        if (i.status === 'fulfilled') setItems(Array.isArray(i.value) ? i.value : []);
        const failures = [c, r, i].filter((x) => x.status === 'rejected');
        if (failures.length === 3) {
          setBootError('Could not reach /api/dev. Is DEBUG / DEV_TOOLS_ENABLED on?');
        }
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  if (loading) return <Loader />;
  if (bootError) return <EmptyState>{bootError}</EmptyState>;

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <div className="font-script text-sheikah-teal-deep text-base flex items-center gap-2">
          <TestTubeDiagonal size={14} /> dev tools · manual testing rig
        </div>
        <p className="text-caption text-ink-secondary leading-relaxed max-w-prose">
          Each card wraps one of the 8 force commands. Pick a target child, set
          parameters, fire — the corresponding UI surface should render in the
          child's session within seconds (toast-poll endpoints) or on next
          mount (App-boot pollers like CelebrationModal). Use the checklist on
          the right to walk every conditional surface in order. Disabled in
          production; gate is parent + DEBUG OR DEV_TOOLS_ENABLED.
        </p>
      </header>

      {children.length === 0 ? (
        <EmptyState>
          No children in your family yet — add one in the Children tab first.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4 items-start">
          <div className="space-y-3">
            <ForceDropCard kids={children} items={items} />
            <ForceCelebrationCard kids={children} />
            <SetStreakCard kids={children} />
            <SetPetHappinessCard kids={children} />
            <ExpireJournalCard kids={children} />
            <SetRewardStockCard rewards={rewards} />
            <ResetDayCountersCard kids={children} />
            <TickPerfectDayCard />
          </div>
          <div className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)]">
            <ChecklistRail />
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Cards ──────────────────────────────────────────────────────── */

function kidOptions(kids) {
  return kids.map((k) => ({ value: k.id, label: k.display_label || k.username }));
}

function useFormFields(initial) {
  const [state, setState] = useState(initial);
  const set = (k) => (e) => {
    const value = e?.target?.type === 'checkbox' ? e.target.checked : (e?.target?.value ?? e);
    setState((prev) => ({ ...prev, [k]: value }));
  };
  return [state, set];
}

function ForceDropCard({ kids, items }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '',
    rarity: 'legendary',
    slug: '',
    count: 1,
    salvage: false,
  });
  const itemOptions = useMemo(
    () => [{ value: '', label: '— pick by rarity —' }].concat(
      items.map((i) => ({ value: i.slug, label: `${i.name} (${i.rarity})` })),
    ),
    [items],
  );

  return (
    <DevToolCard
      title="Force drop"
      description="Writes DropLog + UserInventory directly. Bypasses RNG so RareDropReveal (rare/epic/legendary) and DropToastStack (common/uncommon) are testable on demand."
      buttonLabel="Drop it"
      buildAction={() =>
        devForceDrop({
          user_id: Number(form.user_id),
          rarity: form.slug ? null : form.rarity,
          slug: form.slug || null,
          count: Number(form.count) || 1,
          salvage: form.salvage,
        })
      }
      formatResult={(r) =>
        `✓ ${r.salvaged ? 'Salvaged' : 'Dropped'} ${r.count}× ${r.item.name} (${r.item.rarity})`
      }
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}
        options={kidOptions(kids)} />
      <SelectField label="Rarity" value={form.rarity} onChange={set('rarity')}
        options={[
          { value: 'common', label: 'common' },
          { value: 'uncommon', label: 'uncommon' },
          { value: 'rare', label: 'rare' },
          { value: 'epic', label: 'epic' },
          { value: 'legendary', label: 'legendary' },
        ]}
        helpText={form.slug ? 'Ignored — specific item picked below.' : null}
      />
      <SelectField label="Specific item (optional)" value={form.slug} onChange={set('slug')}
        options={itemOptions} />
      <TextField label="Count" type="number" min="1" max="10"
        value={form.count} onChange={set('count')} />
      <CheckboxField label="Salvage (skip inventory, post coins)" checked={form.salvage}
        onChange={set('salvage')} />
    </DevToolCard>
  );
}

function ForceCelebrationCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '', kind: 'streak_milestone', days: 30, gift_coins: 500,
  });

  return (
    <DevToolCard
      title="Force celebration"
      description="Inserts a notification or chronicle entry that drives CelebrationModal / BirthdayCelebrationModal at next App boot."
      buttonLabel="Celebrate"
      buildAction={() =>
        devForceCelebration({
          user_id: Number(form.user_id),
          kind: form.kind,
          days: Number(form.days),
          gift_coins: Number(form.gift_coins),
        })
      }
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}
        options={kidOptions(kids)} />
      <SelectField label="Kind" value={form.kind} onChange={set('kind')}
        options={[
          { value: 'streak_milestone', label: 'streak milestone' },
          { value: 'perfect_day', label: 'perfect day' },
          { value: 'birthday', label: 'birthday' },
        ]} />
      {form.kind === 'streak_milestone' ? (
        <TextField label="Streak days" type="number" value={form.days}
          onChange={set('days')} helpText="Real milestones: 3 / 7 / 14 / 30 / 60 / 100" />
      ) : null}
      {form.kind === 'birthday' ? (
        <TextField label="Gift coins" type="number" value={form.gift_coins}
          onChange={set('gift_coins')} />
      ) : null}
    </DevToolCard>
  );
}

function SetStreakCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '', days: 29, perfect_days: '',
  });
  return (
    <DevToolCard
      title="Set streak"
      description="Pre-bakes login_streak (and optionally perfect_days_count) so you can test the next-milestone modal without grinding 29 days."
      buttonLabel="Set"
      buildAction={() =>
        devSetStreak({
          user_id: Number(form.user_id),
          days: Number(form.days),
          ...(form.perfect_days !== '' && { perfect_days: Number(form.perfect_days) }),
        })
      }
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}
        options={kidOptions(kids)} />
      <TextField label="Login streak (days)" type="number" value={form.days}
        onChange={set('days')} />
      <TextField label="Perfect days (optional)" type="number" value={form.perfect_days}
        onChange={set('perfect_days')} placeholder="leave blank to skip" />
    </DevToolCard>
  );
}

function SetPetHappinessCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '', level: 'stale', pet_id: '',
  });
  return (
    <DevToolCard
      title="Set pet happiness"
      description="Backdates last_fed_at so the dim filter + whisper text on Companions matches the chosen level. Excludes evolved mounts."
      buttonLabel="Set happiness"
      buildAction={() =>
        devSetPetHappiness({
          user_id: Number(form.user_id),
          level: form.level,
          ...(form.pet_id !== '' && { pet_id: Number(form.pet_id) }),
        })
      }
      formatResult={(r) => `✓ ${r.pets_updated} pet(s) → ${r.level}`}
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}
        options={kidOptions(kids)} />
      <SelectField label="Level" value={form.level} onChange={set('level')}
        options={[
          { value: 'happy', label: 'happy (no dim)' },
          { value: 'bored', label: 'bored (light dim)' },
          { value: 'stale', label: 'stale (medium dim + whisper)' },
          { value: 'away', label: 'away (heavy dim, no whisper)' },
        ]} />
      <TextField label="Pet ID (optional)" type="number" value={form.pet_id}
        onChange={set('pet_id')} placeholder="leave blank for all unevolved" />
    </DevToolCard>
  );
}

function ExpireJournalCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '', days_back: 1,
  });
  return (
    <DevToolCard
      title="Expire journal entry"
      description="Backdates today's journal entry to N days ago so the read-only lock UI engages on open."
      buttonLabel="Expire"
      buildAction={() =>
        devExpireJournal({
          user_id: Number(form.user_id),
          days_back: Number(form.days_back),
        })
      }
      formatResult={(r) => `✓ ${r.action} → ${r.occurred_on}`}
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}
        options={kidOptions(kids)} />
      <TextField label="Days back" type="number" value={form.days_back}
        onChange={set('days_back')} />
    </DevToolCard>
  );
}

function SetRewardStockCard({ rewards }) {
  const [form, set] = useFormFields({
    reward_id: rewards[0]?.id || '', stock: 0,
  });
  if (rewards.length === 0) {
    return (
      <DevToolCard
        title="Set reward stock"
        description="Drives sold-out + last-one chips on Rewards. Add a reward in the Children/Rewards manage tab first."
      >
        <p className="text-caption text-ink-secondary italic">No rewards in your family yet.</p>
      </DevToolCard>
    );
  }
  return (
    <DevToolCard
      title="Set reward stock"
      description="0 = sold out (chip + 409 OOS sheet), 1 = last one chip, N+ = restock. Direct mutation does NOT fire REWARD_RESTOCKED — use Manage UI for that path."
      buttonLabel="Set stock"
      buildAction={() =>
        devSetRewardStock({
          reward_id: Number(form.reward_id),
          stock: Number(form.stock),
        })
      }
      formatResult={(r) => `✓ ${r.name}: ${r.prev_stock ?? '∞'} → ${r.new_stock}`}
    >
      <SelectField label="Reward" value={form.reward_id} onChange={set('reward_id')}
        options={rewards.map((r) => ({
          value: r.id,
          label: `${r.name} · stock ${r.stock ?? '∞'}`,
        }))} />
      <TextField label="New stock" type="number" min="0" value={form.stock}
        onChange={set('stock')} />
    </DevToolCard>
  );
}

function ResetDayCountersCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '', kind: 'all',
  });
  return (
    <DevToolCard
      title="Reset day counters"
      description="Clears today's HomeworkDailyCounter / CreationDailyCounter / MovementDailyCounter rows so first-of-day reward gates re-arm."
      buttonLabel="Reset"
      buildAction={() =>
        devResetDayCounters({
          user_id: Number(form.user_id),
          kind: form.kind,
        })
      }
      formatResult={(r) => {
        const total = Object.values(r.deleted).reduce((a, b) => a + b, 0);
        return `✓ deleted ${total} row(s)`;
      }}
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}
        options={kidOptions(kids)} />
      <SelectField label="Kind" value={form.kind} onChange={set('kind')}
        options={[
          { value: 'all', label: 'all (homework + creation + movement)' },
          { value: 'homework', label: 'homework only' },
          { value: 'creation', label: 'creation only' },
          { value: 'movement', label: 'movement only' },
        ]} />
    </DevToolCard>
  );
}

function TickPerfectDayCard() {
  return (
    <DevToolCard
      title="Tick perfect day"
      description="Runs apps.rpg.tasks.evaluate_perfect_day_task synchronously. The task only awards children who genuinely qualify (active today + ≥1 daily chore + all done) — this just runs it without waiting for 23:55."
      buttonLabel="Tick"
      buildAction={() => devTickPerfectDay()}
      formatResult={(r) => `✓ ${r.task} → ${JSON.stringify(r.result)}`}
    />
  );
}
