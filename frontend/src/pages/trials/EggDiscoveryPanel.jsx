import { useState } from 'react';
import { Link } from 'react-router-dom';
import { getToken } from '../../api/client';
import { useRole } from '../../hooks/useRole';
import { useSpace } from '../../hooks/useSpace';
import useEggDiscoveries from '../../hooks/useEggDiscoveries';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import CatalogIcon from '../../components/rpg/CatalogIcon';
import BottomSheet from '../../components/BottomSheet';
import { TextField } from '../../components/form';
import DiscoveryProgress, { DiscoveryRequirements } from '../../components/egg-discovery/DiscoveryProgress';

function EggIdentity({ discovery }) {
  const egg = discovery.egg_item;
  return <div className="flex items-center gap-3">
    <CatalogIcon spriteKey={egg?.sprite_key} icon={egg?.icon || '🥚'} size={40} alt="Egg" />
    <div className="min-w-0"><h3 className="font-semibold text-body text-ink-primary break-words">{discovery.name}</h3>
      <p className="text-caption text-ink-secondary">{discovery.tier === 'rare' ? 'Rare egg' : 'Ordinary egg'}{discovery.potion_name ? ` · ${discovery.potion_name} potion included` : ''}</p>
    </div>
  </div>;
}

function Season({ season, accepted = false }) {
  if (!season) return null;
  return <p className="text-caption text-ink-secondary">{accepted
    ? 'Seasonal discovery saved. You can finish after the season ends.'
    : `Start between ${season.starts_on} and ${season.ends_on}, inclusive. Once chosen, finish at your own pace.`}</p>;
}

function PracticeForm({ state, onClose }) {
  const [name, setName] = useState('');
  const [minutes, setMinutes] = useState('');
  const submit = async (event) => {
    event.preventDefault();
    const receipt = state.uncertain ? await state.retry() : await state.logPractice({ name: name.trim(), minutes: Number(minutes) });
    if (receipt) onClose();
  };
  return <BottomSheet title="Log making or practice" onClose={onClose} disabled={state.busy} dirty={Boolean(name || minutes || state.uncertain)}>
    <form className="space-y-3" onSubmit={submit}>
      <p className="text-body text-ink-secondary">Record time spent drawing, building, making music, coding, or practicing another skill. Record the same activity time only once.</p>
      <ErrorAlert message={state.actionError} />
      {state.uncertain && <p role="status" className="text-caption text-ink-secondary">We could not confirm this save. Retry the same activity safely before recording another.</p>}
      <fieldset disabled={state.busy || state.uncertain} className="space-y-3 min-w-0">
        <TextField label="What did you make or practice?" value={name} onChange={(event) => setName(event.target.value)} maxLength={100} required error={state.fieldErrors.name} />
        <TextField label="Minutes" type="number" min="1" max="240" step="1" value={minutes} onChange={(event) => setMinutes(event.target.value)} required error={state.fieldErrors.minutes} />
      </fieldset>
      <p className="text-caption text-ink-secondary">Only your active egg discovery receives progress. This log does not add Coins or XP. Reading and movement have their own logs.</p>
      <div className="flex flex-wrap justify-end gap-2"><Button variant="ghost" disabled={state.busy} onClick={onClose}>Cancel</Button><Button type="submit" disabled={state.busy || !name.trim() || !minutes}>{state.busy ? 'Saving…' : state.uncertain ? 'Retry save' : 'Save activity'}</Button></div>
    </form>
  </BottomSheet>;
}

function unavailableMessage(reason) {
  if (typeof reason === 'string' && reason.includes(' ')) return reason;
  return {
    prerequisite: 'Hatch more different companions to unlock this discovery.',
    prerequisites: 'Hatch more different companions to unlock this discovery.',
    season_closed: 'This discovery is outside its start window.',
    already_owned: 'You already have this appearance.',
    already_collected: 'You already have this appearance.',
    already_completed: 'You have already earned this discovery.',
    supplies_owned: 'You already have supplies for this appearance.',
    incubation_pending: 'This appearance is already incubating.',
  }[reason] || 'This egg is not available to start right now.';
}

export default function EggDiscoveryPanel({ refreshKey }) {
  const { user } = useRole();
  const { space } = useSpace();
  return <EggDiscoveryWorkspace key={`${user?.id}:${user?.family?.id}:${getToken()}:${space}`} refreshKey={refreshKey} />;
}

function EggDiscoveryWorkspace({ refreshKey }) {
  const state = useEggDiscoveries({ refreshKey });
  const [practiceOpen, setPracticeOpen] = useState(false);
  if (!state.allowed) return null;
  if (state.loading) return <p role="status" className="text-caption text-ink-secondary">Loading egg discoveries…</p>;
  if (!state.enabled) return state.error ? <ErrorAlert message={state.error} onRetry={state.reload} /> : null;
  const discoveries = state.data?.discoveries || [];
  const active = discoveries.find((row) => row.id === state.data?.active_id && row.status === 'active');
  const paused = discoveries.filter((row) => row.status === 'paused');
  const completed = discoveries.filter((row) => row.status === 'completed');
  const saved = new Set(discoveries.map((row) => row.offer_key));
  const offers = (state.data?.offers || []).filter((row) => !saved.has(row.key));
  const blocked = state.busy || state.uncertain || Boolean(state.error) || state.refreshing;
  return <ParchmentCard>
    <section aria-labelledby="egg-discovery-heading" className="space-y-4">
      <div><h2 id="egg-discovery-heading" className="font-display font-bold text-lede text-ink-primary">Egg discoveries</h2>
        <p className="text-body text-ink-secondary">Choose one egg to work toward through reading, movement, and making or practice. Each discovery includes a compatible potion and starter food. Your saved earlier egg rewards remain available below.</p>
      </div>
      <ErrorAlert message={state.error} onRetry={state.reload} />
      {!practiceOpen && <ErrorAlert message={state.actionError} />}
      {state.refreshing && <p role="status" className="text-caption text-ink-secondary">Refreshing egg discoveries…</p>}
      {state.uncertain && !practiceOpen && <div className="space-y-2"><p role="status" className="text-caption text-ink-secondary">We could not confirm the change. Retry safely with the same request.</p><Button disabled={state.busy} variant="secondary" onClick={state.retry}>Retry change</Button></div>}
      {active ? <section aria-label="Your active egg discovery" className="rounded-xl border border-ink-page-shadow p-4 space-y-3">
        <EggIdentity discovery={active} />
        <DiscoveryProgress discovery={active} />
        <Season season={active.season} accepted />
        {!active.delivery_pending && <p className="text-caption text-ink-secondary">Reading and movement logs dated today contribute when recorded. Short sessions accumulate. Search results happen automatically; there is nothing to claim.</p>}
        <div className="flex flex-wrap gap-2">
          {active.delivery_pending ? <Button variant="secondary" disabled={blocked} onClick={() => state.select(active.offer_key)}>Try delivery again</Button> : <>
          <Link className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep" to="/quests?tab=reading">Log reading</Link>
          <Link className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep" to="/quests?tab=movement&log=1">Log movement</Link>
          <Button variant="secondary" disabled={blocked} onClick={() => setPracticeOpen(true)}>Log making or practice</Button>
          </>}
          <Button variant="ghost" disabled={blocked} onClick={() => state.pause(active.id)}>Pause discovery</Button>
        </div>
      </section> : state.enabled && <p className="text-body text-ink-secondary">Choose an egg below or resume a saved discovery. Only one discovery receives new activity at a time.</p>}
      {paused.length > 0 && <section aria-label="Paused egg discoveries" className="space-y-3">
        <h3 className="font-semibold text-body text-ink-primary">Saved for later</h3>
        {active && <p className="text-caption text-ink-secondary">Resuming a saved discovery or trying its delivery pauses your current discovery and saves its progress.</p>}
        {paused.map((row) => <div key={row.id} className="rounded-xl border border-ink-page-shadow p-3 space-y-3"><EggIdentity discovery={row} /><DiscoveryProgress discovery={row} /><Season season={row.season} accepted />
          <Button variant="secondary" disabled={blocked || row.can_resume === false} onClick={() => state.select(row.offer_key)}>{row.delivery_pending ? 'Try delivery again' : `Resume ${row.name}`}</Button>
        </div>)}
      </section>}
      {completed.length > 0 && <details open={!active} className="space-y-3"><summary className="min-h-11 cursor-pointer font-semibold text-body text-ink-primary">Earned eggs · {completed.length}</summary>
        {completed.map((row) => <section aria-label={`Earned ${row.name}`} key={row.id} className="rounded-xl border border-ink-page-shadow p-3 space-y-3"><EggIdentity discovery={row} /><DiscoveryProgress discovery={row} />
          {row.receipt?.items?.length > 0 && <ul aria-label="Discovery supplies" className="text-caption text-ink-secondary">{row.receipt.items.map((item) => <li key={item.item_id}>{item.item_name} × {item.quantity}</li>)}</ul>}
          <Link className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep" to="/bestiary?tab=hatchery">Take your egg to the Hatchery</Link>
        </section>)}
      </details>}
      {state.enabled && <section aria-label="Available egg discoveries" className="space-y-3">
        <details key={active?.id ?? 'choose'} open={active ? undefined : true} className="space-y-3">
        <summary className="min-h-11 cursor-pointer font-semibold text-body text-ink-primary">{active ? 'Choose another egg' : 'Choose an egg'}</summary>
        {active && <p className="text-caption text-ink-secondary">Choosing another egg pauses your current discovery and saves its progress. Recorded minutes stay with the egg they helped.</p>}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{offers.map((offer) => <div key={offer.key} className="rounded-xl border border-ink-page-shadow p-3 space-y-3"><EggIdentity discovery={offer} /><DiscoveryRequirements requirements={offer.requirements} /><Season season={offer.season} />
          {!offer.eligible && <p className="text-caption text-ink-secondary">{unavailableMessage(offer.unavailable_reason)}</p>}
          <Button variant="secondary" disabled={blocked || !offer.eligible} onClick={() => state.select(offer.key)}>Choose {offer.name}</Button>
        </div>)}</div>
        {!offers.length && <p className="text-caption text-ink-secondary">No other eggs are available to start right now.</p>}
        </details>
      </section>}
      {practiceOpen && <PracticeForm state={state} onClose={() => setPracticeOpen(false)} />}
    </section>
  </ParchmentCard>;
}
