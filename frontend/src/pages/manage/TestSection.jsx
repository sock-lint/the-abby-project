import { useEffect, useMemo, useState } from 'react';
import { TestTubeDiagonal } from 'lucide-react';
import EmptyState from '../../components/EmptyState';
import Loader from '../../components/Loader';
import { TextField, SelectField, CheckboxField } from '../../components/form';
import {
  devClearBreedCooldowns,
  devForceApprovalNotification,
  devForceCelebration,
  devForceDrop,
  devForceQuestProgress,
  devGrantHatchIngredients,
  devMarkDailyChallengeReady,
  devMarkExpeditionReady,
  devExpireJournal,
  devResetDayCounters,
  devSeedCompanionGrowth,
  devSetPetGrowth,
  devSetPetHappiness,
  devSetRewardStock,
  devSetStreak,
  devTickPerfectDay,
  devToolsChildren,
  devToolsItems,
  devToolsPetSpecies,
  devToolsPotionTypes,
  devToolsRewards,
} from '../../api';
import ChecklistRail from './test/ChecklistRail';
import DevToolCard from './test/DevToolCard';
import { ChecklistProvider } from './test/ChecklistContext';

/**
 * TestSection — parent + DEBUG/DEV_TOOLS_ENABLED only.
 *
 * The Manage tab calls /api/dev/ping/ before rendering this section so
 * we never mount when the gate is off. Inside, each card wraps one
 * /api/dev/* endpoint with a tiny inline form. Each card also declares
 * a ``checklistId`` matching the stable `<!-- id:slug -->` annotation
 * on the same surface in docs/manual-testing.md — the result line
 * surfaces a "Mark verified" button that ticks the row in the rail.
 */
export default function TestSection() {
  const [children, setChildren] = useState([]);
  const [rewards, setRewards] = useState([]);
  const [items, setItems] = useState([]);
  const [petSpecies, setPetSpecies] = useState([]);
  const [potionTypes, setPotionTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [bootError, setBootError] = useState('');

  useEffect(() => {
    let alive = true;
    Promise.allSettled([
      devToolsChildren(),
      devToolsRewards(),
      devToolsItems(),
      devToolsPetSpecies(),
      devToolsPotionTypes(),
    ])
      .then(([c, r, i, s, p]) => {
        if (!alive) return;
        if (c.status === 'fulfilled') setChildren(Array.isArray(c.value) ? c.value : []);
        if (r.status === 'fulfilled') setRewards(Array.isArray(r.value) ? r.value : []);
        if (i.status === 'fulfilled') setItems(Array.isArray(i.value) ? i.value : []);
        if (s.status === 'fulfilled') setPetSpecies(Array.isArray(s.value) ? s.value : []);
        if (p.status === 'fulfilled') setPotionTypes(Array.isArray(p.value) ? p.value : []);
        const failures = [c, r, i, s, p].filter((x) => x.status === 'rejected');
        if (failures.length === 5) {
          setBootError('Could not reach /api/dev. Is DEBUG / DEV_TOOLS_ENABLED on?');
        }
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  if (loading) return <Loader />;
  if (bootError) return <EmptyState>{bootError}</EmptyState>;

  return (
    <ChecklistProvider>
      <div className="space-y-4">
        <header className="space-y-1">
          <div className="font-script text-sheikah-teal-deep text-base flex items-center gap-2">
            <TestTubeDiagonal size={14} /> dev tools · manual testing rig
          </div>
          <p className="text-caption text-ink-secondary leading-relaxed max-w-prose">
            Each card wraps one /api/dev/* command. Pick a target child, set
            parameters, fire — the corresponding UI surface should render in the
            child&apos;s session within seconds (toast-poll endpoints) or on next
            mount (App-boot pollers like CelebrationModal). After verifying on
            the kid&apos;s session, tap &ldquo;Mark verified&rdquo; to tick the
            linked row in the checklist on the right. Disabled in production;
            gate is parent + DEBUG OR DEV_TOOLS_ENABLED.
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
              <ForceApprovalNotificationCard kids={children} />
              <ForceQuestProgressCard kids={children} />
              <MarkDailyChallengeReadyCard kids={children} />
              <SetPetGrowthCard kids={children} />
              <GrantHatchIngredientsCard
                kids={children}
                petSpecies={petSpecies}
                potionTypes={potionTypes}
              />
              <ClearBreedCooldownsCard kids={children} />
              <SeedCompanionGrowthCard kids={children} />
              <MarkExpeditionReadyCard kids={children} />
            </div>
            <div className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)]">
              <ChecklistRail />
            </div>
          </div>
        )}
      </div>
    </ChecklistProvider>
  );
}

/* ── Cards ──────────────────────────────────────────────────────── */

function useFormFields(initial) {
  const [state, setState] = useState(initial);
  const set = (k) => (e) => {
    const value = e?.target?.type === 'checkbox' ? e.target.checked : (e?.target?.value ?? e);
    setState((prev) => ({ ...prev, [k]: value }));
  };
  return [state, set];
}

function KidOptions({ kids }) {
  return (
    <>
      {kids.map((k) => (
        <option key={k.id} value={k.id}>{k.display_label || k.username}</option>
      ))}
    </>
  );
}

function ForceDropCard({ kids, items }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '',
    rarity: 'legendary',
    slug: '',
    count: 1,
    salvage: false,
  });

  return (
    <DevToolCard
      title="Force drop"
      description="Writes DropLog + UserInventory directly. Bypasses RNG so RareDropReveal (rare/epic/legendary) and DropToastStack (common/uncommon) are testable on demand."
      buttonLabel="Drop it"
      checklistId="force-drop"
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
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <SelectField
        label="Rarity" value={form.rarity} onChange={set('rarity')}
        helpText={form.slug ? 'Ignored — specific item picked below.' : null}
      >
        <option value="common">common</option>
        <option value="uncommon">uncommon</option>
        <option value="rare">rare</option>
        <option value="epic">epic</option>
        <option value="legendary">legendary</option>
      </SelectField>
      <SelectField label="Specific item (optional)" value={form.slug} onChange={set('slug')}>
        <option value="">— pick by rarity —</option>
        {items.map((i) => (
          <option key={i.slug} value={i.slug}>{i.name} ({i.rarity})</option>
        ))}
      </SelectField>
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
      checklistId="force-celebration"
      buildAction={() =>
        devForceCelebration({
          user_id: Number(form.user_id),
          kind: form.kind,
          days: Number(form.days),
          gift_coins: Number(form.gift_coins),
        })
      }
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <SelectField label="Kind" value={form.kind} onChange={set('kind')}>
        <option value="streak_milestone">streak milestone</option>
        <option value="perfect_day">perfect day</option>
        <option value="birthday">birthday</option>
      </SelectField>
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
      checklistId="set-streak"
      buildAction={() =>
        devSetStreak({
          user_id: Number(form.user_id),
          days: Number(form.days),
          ...(form.perfect_days !== '' && { perfect_days: Number(form.perfect_days) }),
        })
      }
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
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
      checklistId="set-pet-happiness"
      buildAction={() =>
        devSetPetHappiness({
          user_id: Number(form.user_id),
          level: form.level,
          ...(form.pet_id !== '' && { pet_id: Number(form.pet_id) }),
        })
      }
      formatResult={(r) => `✓ ${r.pets_updated} pet(s) → ${r.level}`}
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <SelectField label="Level" value={form.level} onChange={set('level')}>
        <option value="happy">happy (no dim)</option>
        <option value="bored">bored (light dim)</option>
        <option value="stale">stale (medium dim + whisper)</option>
        <option value="away">away (heavy dim, no whisper)</option>
      </SelectField>
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
      checklistId="expire-journal"
      buildAction={() =>
        devExpireJournal({
          user_id: Number(form.user_id),
          days_back: Number(form.days_back),
        })
      }
      formatResult={(r) => `✓ ${r.action} → ${r.occurred_on}`}
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
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
      checklistId="set-reward-stock"
      buildAction={() =>
        devSetRewardStock({
          reward_id: Number(form.reward_id),
          stock: Number(form.stock),
        })
      }
      formatResult={(r) => `✓ ${r.name}: ${r.prev_stock ?? '∞'} → ${r.new_stock}`}
    >
      <SelectField label="Reward" value={form.reward_id} onChange={set('reward_id')}>
        {rewards.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name} · stock {r.stock ?? '∞'}
          </option>
        ))}
      </SelectField>
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
      checklistId="reset-day-counters"
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
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <SelectField label="Kind" value={form.kind} onChange={set('kind')}>
        <option value="all">all (homework + creation + movement)</option>
        <option value="homework">homework only</option>
        <option value="creation">creation only</option>
        <option value="movement">movement only</option>
      </SelectField>
    </DevToolCard>
  );
}

function TickPerfectDayCard() {
  return (
    <DevToolCard
      title="Tick perfect day"
      description="Runs apps.rpg.tasks.evaluate_perfect_day_task synchronously. The task only awards children who genuinely qualify (active today + ≥1 daily chore + all done) — this just runs it without waiting for 23:55."
      buttonLabel="Tick"
      checklistId="tick-perfect-day"
      buildAction={() => devTickPerfectDay()}
      formatResult={(r) => `✓ ${r.task} → ${JSON.stringify(r.result)}`}
    />
  );
}

/* ── Toast & ceremony cards (added 2026-05-11) ──────────────────── */

function ForceApprovalNotificationCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '',
    flow: 'chore',
    outcome: 'approved',
    note: '',
  });
  return (
    <DevToolCard
      title="Force approval notification"
      description="Inserts one of the 12 approval-style notifications useApprovalToasts watches. Drives ApprovalToastStack on the kid's session within 30s. Reject + note lands in the toast body."
      buttonLabel="Send"
      checklistId="force-approval-notification"
      buildAction={() =>
        devForceApprovalNotification({
          user_id: Number(form.user_id),
          flow: form.flow,
          outcome: form.outcome,
          note: form.note || '',
        })
      }
      formatResult={(r) => `✓ ${r.notification_type}`}
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <SelectField label="Flow" value={form.flow} onChange={set('flow')}>
        <option value="chore">chore</option>
        <option value="homework">homework</option>
        <option value="creation">creation</option>
        <option value="exchange">exchange</option>
        <option value="chore_proposal">chore proposal</option>
        <option value="habit_proposal">habit proposal</option>
      </SelectField>
      <SelectField label="Outcome" value={form.outcome} onChange={set('outcome')}>
        <option value="approved">approved</option>
        <option value="rejected">rejected</option>
      </SelectField>
      {form.outcome === 'rejected' ? (
        <TextField label="Reject note (optional)" value={form.note}
          onChange={set('note')} placeholder="lands in the toast body" />
      ) : null}
    </DevToolCard>
  );
}

function ForceQuestProgressCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '', delta: 10,
  });
  return (
    <DevToolCard
      title="Force quest progress"
      description="Bumps the kid's active quest's current_progress by delta (or starts the first eligible system quest first). useQuestProgressToasts polls every 30s and emits the +N floater on detection."
      buttonLabel="Bump"
      checklistId="force-quest-progress"
      buildAction={() =>
        devForceQuestProgress({
          user_id: Number(form.user_id),
          delta: Number(form.delta) || 10,
        })
      }
      formatResult={(r) =>
        `✓ ${r.definition_name}: ${r.current_progress}/${r.target_value} (${r.progress_percent}%)`
      }
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <TextField label="Delta" type="number" min="1" max="1000"
        value={form.delta} onChange={set('delta')} />
    </DevToolCard>
  );
}

function MarkDailyChallengeReadyCard({ kids }) {
  const [form, set] = useFormFields({ user_id: kids[0]?.id || '' });
  return (
    <DevToolCard
      title="Mark daily challenge ready"
      description="Forces today's DailyChallenge to current=target without setting claimed_at. The dashboard renders the gold-leaf ring on tap → DailyChallengeClaimModal opens."
      buttonLabel="Ready"
      checklistId="mark-daily-challenge-ready"
      buildAction={() =>
        devMarkDailyChallengeReady({
          user_id: Number(form.user_id),
        })
      }
      formatResult={(r) =>
        `✓ ${r.kind}: ${r.current_progress}/${r.target_value} · +${r.coin_reward}c +${r.xp_reward}xp`
      }
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
    </DevToolCard>
  );
}

function SetPetGrowthCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '', pet_id: '', growth: 99,
  });
  const kid = useMemo(
    () => kids.find((k) => String(k.id) === String(form.user_id)),
    [kids, form.user_id],
  );
  const pets = (kid?.pets || []).filter((p) => !p.evolved);

  return (
    <DevToolCard
      title="Set pet growth (near-evolution)"
      description="Direct-assigns growth_points so the next feed pushes the pet over 100 and fires PetCeremonyModal (mode=evolve). Bypasses the consumable daily cap."
      buttonLabel="Set growth"
      checklistId="set-pet-growth"
      buildAction={() =>
        devSetPetGrowth({
          user_id: Number(form.user_id),
          pet_id: Number(form.pet_id),
          growth: Number(form.growth),
        })
      }
      formatResult={(r) => `✓ ${r.species_name} → ${r.growth_points}/100`}
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <SelectField
        label="Pet"
        value={form.pet_id}
        onChange={set('pet_id')}
        helpText={
          pets.length === 0
            ? 'No unevolved pets — hatch one first.'
            : null
        }
      >
        <option value="">— pick a pet —</option>
        {pets.map((p) => (
          <option key={p.id} value={p.id}>
            {p.species_name} ({p.potion_name}) · {p.growth_points}/100
          </option>
        ))}
      </SelectField>
      <TextField label="Growth" type="number" min="0" max="99"
        value={form.growth} onChange={set('growth')} />
    </DevToolCard>
  );
}

function GrantHatchIngredientsCard({ kids, petSpecies, potionTypes }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '',
    species_slug: petSpecies[0]?.slug || '',
    potion_slug: potionTypes[0]?.slug || '',
  });
  return (
    <DevToolCard
      title="Grant hatch ingredients"
      description="Drops one matching egg + one matching potion into the kid's inventory. The kid hatches in the Hatchery → PetCeremonyModal (mode=hatch) fires."
      buttonLabel="Grant"
      checklistId="grant-hatch-ingredients"
      buildAction={() =>
        devGrantHatchIngredients({
          user_id: Number(form.user_id),
          species_slug: form.species_slug,
          potion_slug: form.potion_slug,
        })
      }
      formatResult={(r) => `✓ ${r.egg.name} + ${r.potion.name}`}
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <SelectField label="Species" value={form.species_slug} onChange={set('species_slug')}>
        {petSpecies.length === 0
          ? <option value="">no species seeded</option>
          : petSpecies.map((s) => (
              <option key={s.slug} value={s.slug}>{s.icon} {s.name}</option>
            ))}
      </SelectField>
      <SelectField label="Potion" value={form.potion_slug} onChange={set('potion_slug')}>
        {potionTypes.length === 0
          ? <option value="">no potions seeded</option>
          : potionTypes.map((p) => (
              <option key={p.slug} value={p.slug}>{p.name} ({p.rarity})</option>
            ))}
      </SelectField>
    </DevToolCard>
  );
}

function ClearBreedCooldownsCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '', mount_id: '',
  });
  const kid = useMemo(
    () => kids.find((k) => String(k.id) === String(form.user_id)),
    [kids, form.user_id],
  );
  const mounts = kid?.mounts || [];

  return (
    <DevToolCard
      title="Clear mount breed cooldowns"
      description="Sets last_bred_at=None on one or all mounts so the kid can breed immediately in the Hatchery → PetCeremonyModal (mode=breed) fires."
      buttonLabel="Clear"
      checklistId="clear-breed-cooldowns"
      buildAction={() =>
        devClearBreedCooldowns({
          user_id: Number(form.user_id),
          ...(form.mount_id !== '' && { mount_id: Number(form.mount_id) }),
        })
      }
      formatResult={(r) => `✓ ${r.mounts_reset} mount(s) reset`}
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <SelectField label="Mount (optional)" value={form.mount_id} onChange={set('mount_id')}>
        <option value="">— all of this kid&apos;s mounts —</option>
        {mounts.map((m) => (
          <option key={m.id} value={m.id}>
            {m.species_name} ({m.potion_name})
          </option>
        ))}
      </SelectField>
    </DevToolCard>
  );
}

function SeedCompanionGrowthCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '', ticks: 3, force_evolve: false,
  });
  return (
    <DevToolCard
      title="Seed companion growth"
      description="Synthesizes N entries on pending_companion_growth. The kid's useCompanionGrowthToasts polls and renders moss-toned slide-ins. Force evolve flags the last entry → PetCeremonyModal (mode=evolve)."
      buttonLabel="Seed"
      checklistId="seed-companion-growth"
      buildAction={() =>
        devSeedCompanionGrowth({
          user_id: Number(form.user_id),
          ticks: Number(form.ticks) || 3,
          force_evolve: form.force_evolve,
        })
      }
      formatResult={(r) =>
        `✓ seeded ${r.events_seeded} event(s)${r.has_evolve_event ? ' + evolve' : ''}`
      }
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <TextField label="Ticks" type="number" min="1" max="10"
        value={form.ticks} onChange={set('ticks')} />
      <CheckboxField
        label="Force evolve on the last entry"
        checked={form.force_evolve}
        onChange={set('force_evolve')}
      />
    </DevToolCard>
  );
}

function MarkExpeditionReadyCard({ kids }) {
  const [form, set] = useFormFields({
    user_id: kids[0]?.id || '', mount_id: '', tier: 'standard',
  });
  const kid = useMemo(
    () => kids.find((k) => String(k.id) === String(form.user_id)),
    [kids, form.user_id],
  );
  const freeMounts = (kid?.mounts || []).filter((m) => !m.has_active_expedition);

  return (
    <DevToolCard
      title="Mark expedition ready"
      description="Starts an expedition through the real start() service then backdates so it reads ready immediately. The kid's ExpeditionToastStack polls and shows the claim CTA → PetCeremonyModal (mode=expedition_return)."
      buttonLabel="Run + ready"
      checklistId="mark-expedition-ready"
      buildAction={() =>
        devMarkExpeditionReady({
          user_id: Number(form.user_id),
          ...(form.mount_id !== '' && { mount_id: Number(form.mount_id) }),
          tier: form.tier,
        })
      }
      formatResult={(r) =>
        `✓ ${r.species_name} returned (${r.tier}) · ${r.coins ?? '?'}c + ${r.item_count} item(s)`
      }
    >
      <SelectField label="Target" value={form.user_id} onChange={set('user_id')}>
        <KidOptions kids={kids} />
      </SelectField>
      <SelectField
        label="Mount (optional)"
        value={form.mount_id}
        onChange={set('mount_id')}
        helpText={
          freeMounts.length === 0
            ? 'No free mount available — evolve a pet first.'
            : null
        }
      >
        <option value="">— first available —</option>
        {freeMounts.map((m) => (
          <option key={m.id} value={m.id}>
            {m.species_name} ({m.potion_name})
          </option>
        ))}
      </SelectField>
      <SelectField label="Tier" value={form.tier} onChange={set('tier')}>
        <option value="short">short (2h, ~15c)</option>
        <option value="standard">standard (4h, ~35c)</option>
        <option value="long">long (8h, ~75c)</option>
      </SelectField>
    </DevToolCard>
  );
}
