import { useEffect, useRef, useState } from 'react';
import { listProgressionExperiments, createProgressionExperiment, getProgressionExperiment, updateProgressionExperiment, compareProgressionExperiment, getProgressionComparison, recordProgressionDecision, getProgressionObservations, saveProgressionObservation } from '../../api/progressionExperiments';
import { getToken } from '../../api/client';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import ConfirmDialog from '../../components/ConfirmDialog';
import ParchmentCard from '../../components/journal/ParchmentCard';
import SectionHeader from '../../components/SectionHeader';
import { SelectField, TextAreaField, TextField } from '../../components/form';
import ProgressionExpeditionBudgetControls from './ProgressionExpeditionBudgetControls';
import { challengeGateLabel, expeditionBudgetLabel, rewardPolicyLabel, scenariosMatch } from './progressionLabScenario';
import { ExperimentComparison, ProgressionObservations, RewardProposal } from './ProgressionExperimentEvidence';
import ProgressionChallengeGateControls from './ProgressionChallengeGateControls';
const clone = (value) => JSON.parse(JSON.stringify(value));
const unlimited = () => ({ daily_launches: null, daily_items: null });
const gatePolicy = (policy) => ['milestone_gates', 'tenure_gates'].includes(policy);
const controlRoutine = (routine, policy = 'envelope') => gatePolicy(policy)
  ? { ...clone(routine), challenge_gates: { ...clone(routine.challenge_gates), mode: 'current' } }
  : { ...clone(routine), expedition_budget: unlimited(), ...(policy === 'expedition_limits' ? {} : { reward_budget: { daily_coins: null }, reward_commitment: { enabled: false } }) };
const fields = (experiment) => ({ name: experiment.name, hypothesis: experiment.hypothesis, config: clone(experiment.config), candidate_daily_coins: experiment.candidate_daily_coins, candidate_policy: experiment.candidate_policy ?? 'envelope', candidate_expedition_budget: clone(experiment.candidate_expedition_budget ?? unlimited()), targets: experiment.targets.map((target) => ({ metric: target.metric, min: target.min ?? '', max: target.max ?? '' })) });
const freshEditor = (routine) => ({ name: '100-Coin starting experiment', hypothesis: 'Reduce automatic Coin income while preserving reward pacing.', config: controlRoutine(routine), candidate_daily_coins: 100, candidate_policy: 'envelope', candidate_expedition_budget: unlimited(), targets: [] });
const decisionLabels = { keep_testing: 'Keep testing', revise: 'Revise', ready_for_design: 'Ready for design' };
const blankDecision = { outcome: 'keep_testing', rationale: '', next_action: '', review_on: '' };

export default function ProgressionExperimentNotebook({ routine, gateMetadata }) {
  const [metadata, setMetadata] = useState(null);
  const [observations, setObservations] = useState(null);
  const [loading, setLoading] = useState(true);
  const [observationLoading, setObservationLoading] = useState(true);
  const [readError, setReadError] = useState(null);
  const [observationError, setObservationError] = useState(null);
  const [denied, setDenied] = useState(false);
  const [saved, setSaved] = useState(null);
  const [editor, setEditor] = useState(() => freshEditor(routine));
  const [comparison, setComparison] = useState(null);
  const [decision, setDecision] = useState(blankDecision);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  const active = useRef(false);
  const requests = useRef(new Set());
  const token = getToken();
  const dirty = saved ? !scenariosMatch(editor, fields(saved)) : !scenariosMatch(editor, freshEditor(routine));
  const decisionDirty = !scenariosMatch(decision, blankDecision);
  usePwaUpdateGuard(dirty || decisionDirty || busy);
  const current = () => active.current && token === getToken();
  const controller = () => { const value = new AbortController(); requests.current.add(value); return value; };
  const read = async () => {
    const request = controller(); setLoading(true); setReadError(null);
    try { const data = await listProgressionExperiments({ signal: request.signal }); if (current()) setMetadata(data); }
    catch (failure) { if (current() && failure.name !== 'AbortError') { if ([401, 403].includes(failure.status)) setDenied(true); else setReadError(`Could not load saved experiments. ${failure.message}`); } }
    finally { requests.current.delete(request); if (current()) setLoading(false); }
  };
  const readObservations = async () => {
    const request = controller(); setObservationLoading(true); setObservationError(null);
    try { const data = await getProgressionObservations({ signal: request.signal }); if (current()) setObservations(data); }
    catch (failure) { if (current() && failure.name !== 'AbortError') setObservationError(`Could not load observed evidence. ${failure.message} ${observations ? 'The previous successful evidence remains displayed; it is not a current read.' : 'No observation result is available.'}`); }
    finally { requests.current.delete(request); if (current()) setObservationLoading(false); }
  };
  useEffect(() => {
    active.current = true; read(); readObservations();
    const pending = requests.current;
    return () => { active.current = false; pending.forEach((request) => request.abort()); };
    // The owning Lab remounts on account, family or credential replacement.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const change = (key, value) => setEditor((previous) => ({ ...previous, [key]: value }));
  const changePolicy = (policy) => setEditor((previous) => ({ ...previous, candidate_policy: policy, config: controlRoutine(gatePolicy(policy) ? (gatePolicy(previous.candidate_policy) ? previous.config : { ...routine, challenge_gates: routine.challenge_gates ?? gateMetadata.challenge_gates_defaults }) : policy === 'expedition_limits' ? routine : previous.config, policy), candidate_daily_coins: policy === 'expedition_limits' || gatePolicy(policy) ? null : 100, candidate_expedition_budget: policy === 'expedition_limits' ? clone(routine.expedition_budget?.daily_launches != null || routine.expedition_budget?.daily_items != null ? routine.expedition_budget : { daily_launches: 3, daily_items: null }) : unlimited() }));
  const remember = (data) => {
    setSaved(data); setEditor(fields(data));
    setMetadata((previous) => ({ ...previous, experiments: [data, ...previous.experiments.filter((entry) => entry.id !== data.id)] }));
  };
  const run = async (operation, success) => {
    if (busy) return;
    const request = controller(); setBusy(true); setError(null); setNotice(null);
    try { const response = await operation({ signal: request.signal }); if (current()) success(response); }
    catch (failure) {
      if (current() && failure.name !== 'AbortError') {
        if ([401, 403].includes(failure.status)) setDenied(true);
        else { setError(`${failure.message} Your inputs and saved evidence have been kept.${failure.status === 409 ? ' Reload the saved experiment and review it before continuing.' : ''}`); if (failure.status === 409) setComparison((previous) => previous && { ...previous, stale: true, freshness: 'stale' }); }
      }
    } finally { requests.current.delete(request); if (current()) setBusy(false); }
  };
  const guard = (action) => {
    if (dirty || decisionDirty) setConfirmation({ action, discardEditor: true }); else action();
  };
  const guardDecision = (action) => { if (decisionDirty) setConfirmation({ action, discardEditor: false }); else action(); };
  const open = (id) => guard(() => {
    if (!id) { setSaved(null); setEditor(freshEditor(routine)); setComparison(null); setDecision(blankDecision); setNotice(null); return; }
    run((options) => getProgressionExperiment(id, options), (data) => { remember(data); setComparison(null); setDecision(blankDecision); setNotice('Saved experiment loaded.'); });
  });
  const save = (event) => {
    event.preventDefault();
    const targets = editor.targets.map((target) => ({ metric: target.metric, min: target.min === '' ? null : Number(target.min), max: target.max === '' ? null : Number(target.max) }));
    if (targets.some((target) => target.min === null && target.max === null)) { setError('Each success criterion needs a minimum or maximum. Remove an unused criterion.'); return; }
    const payload = { ...editor, config: controlRoutine(editor.config, editor.candidate_policy), targets };
    guardDecision(() => run((options) => saved ? updateProgressionExperiment(saved.id, { revision: saved.revision, ...payload }, options) : createProgressionExperiment(payload, options), (data) => { remember(data); setComparison(null); setDecision(blankDecision); setNotice('Experiment saved. Live rewards are unchanged.'); }));
  };
  const compare = () => guardDecision(() => run((options) => compareProgressionExperiment(saved.id, { revision: saved.revision }, options), (data) => {
    setComparison(data); setSaved((previous) => ({ ...previous, comparisons: [data, ...previous.comparisons] })); setDecision(blankDecision); setNotice('Control and candidate comparison saved.');
  }));
  const openComparison = (id) => guard(() => {
    if (!id) { setComparison(null); return; }
    run((options) => getProgressionComparison(saved.id, id, options), (data) => { setComparison(data); setDecision(blankDecision); });
  });
  const recordDecision = (event) => {
    event.preventDefault();
    run((options) => recordProgressionDecision(saved.id, { revision: saved.revision, comparison_id: comparison.id, ...decision }, options), (data) => { remember(data); setDecision(blankDecision); setNotice('Decision recorded. No live changes were approved.'); });
  };
  const canDecide = comparison && !comparison.stale && comparison.freshness === 'current' && comparison.experiment_revision === saved?.revision && !dirty;
  const target = (index, key, value) => change('targets', editor.targets.map((row, position) => position === index ? { ...row, [key]: value } : row));
  if (denied) return <p role="status">Saved experiments are available to staff parents.</p>;
  return <section aria-label="Progression experiment notebook" className="space-y-4">
    <ParchmentCard className="space-y-4">
      <SectionHeader title="Experiment notebook" index={3}>Save a hypothesis, compare Coin policies, shared expedition limits or challenge gates, then record what to do next. No decision here changes live rewards.</SectionHeader>
      <ErrorAlert message={readError} onRetry={read} />
      {loading && <p role="status">Loading saved experiments…</p>}
      {metadata && <>
        <div className="flex flex-wrap gap-3 items-end"><SelectField label="Open experiment" value={saved?.id ?? ''} disabled={busy} onChange={(event) => open(event.target.value)} className="flex-1 min-w-0"><option value="">New experiment</option>{metadata.experiments.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} · revision {entry.revision}{entry.latest_decision ? ` · ${decisionLabels[entry.latest_decision.outcome]}` : ''}</option>)}</SelectField>{saved && <Button variant="ghost" disabled={busy} onClick={() => open(saved.id)}>Reload saved experiment</Button>}</div>
        <form aria-label="Save progression experiment" onSubmit={save} className="space-y-4">
          <fieldset disabled={busy} className="min-w-0 space-y-3"><legend className="sr-only">Experiment assumptions</legend>
            <TextField label="Experiment name" value={editor.name} maxLength={100} required onChange={(event) => change('name', event.target.value)} />
            <TextAreaField label="Hypothesis" value={editor.hypothesis} maxLength={2000} required onChange={(event) => change('hypothesis', event.target.value)} helpText="Describe the expected improvement. Use anonymous design notes without child names or private family details." />
            <SelectField label="Candidate reward policy" value={editor.candidate_policy} onChange={(event) => changePolicy(event.target.value)}>
              <option value="envelope">Hypothetical payout envelope</option><option value="commitment100">100-Coin commitment prototype (75 / 25)</option>{metadata.feedback.expedition_budget_limits && <option value="expedition_limits">Shared expedition limits (same Coin rules)</option>}{gateMetadata?.challenge_gates_defaults && <><option value="milestone_gates">Milestone gates (same rewards and expeditions)</option><option value="tenure_gates">Milestone plus tenure gates (same rewards and expeditions)</option></>}
            </SelectField>
            {editor.candidate_policy !== 'expedition_limits' && !gatePolicy(editor.candidate_policy) && <TextField disabled={editor.candidate_policy === 'commitment100'} label="Candidate Coins per child per day" type="number" min={0} max={100000} step="1" required value={editor.candidate_daily_coins} onChange={(event) => change('candidate_daily_coins', event.target.value === '' ? '' : Number(event.target.value))} />}
            {editor.candidate_policy === 'expedition_limits' && <ProgressionExpeditionBudgetControls label="Candidate expedition limits" budget={editor.candidate_expedition_budget} limits={metadata.feedback.expedition_budget_limits} onChange={(budget) => change('candidate_expedition_budget', budget)} />}
            {gatePolicy(editor.candidate_policy) && gateMetadata && <ProgressionChallengeGateControls label="Candidate challenge gates" modeLocked gates={{ ...editor.config.challenge_gates, mode: editor.candidate_policy === 'milestone_gates' ? 'milestones' : 'milestone_tenure' }} metadata={gateMetadata} onChange={(gates) => change('config', { ...editor.config, challenge_gates: { ...gates, mode: 'current' } })} />}
            <p className="text-body text-ink-secondary">Saved routine: {editor.config.horizon_days} days, {editor.config.trials} simulated children, seed {editor.config.seed}. {gatePolicy(editor.candidate_policy) ? `Control uses current challenge rules; the candidate uses ${editor.candidate_policy === 'milestone_gates' ? 'milestone gates' : 'milestone plus tenure gates'}. Both arms keep ${rewardPolicyLabel(editor.config)} and ${expeditionBudgetLabel(editor.config.expedition_budget)}.` : editor.candidate_policy === 'expedition_limits' ? `Control and candidate both use ${rewardPolicyLabel(editor.config)}. The control has unlimited expeditions; only the candidate launch or item limits change.` : 'Control uses installed reward rules.'} {gatePolicy(editor.candidate_policy) ? 'Waiting and unreachable challenges must be reviewed alongside reward timing.' : editor.candidate_policy === 'expedition_limits' ? '' : editor.candidate_policy === 'commitment100' ? 'The candidate reserves new promises before launch or drop, with 75 Coins for expeditions and 25 for random activity pouches. Existing and authored promises pay fully.' : 'The candidate omits excess expedition and pouch payouts in a hypothetical shared daily envelope.'}</p>
            {!gatePolicy(editor.candidate_policy) && <p className="text-caption text-ink-secondary">Both arms keep the same challenge gates: {challengeGateLabel(editor.config.challenge_gates)}.</p>}
            {!scenariosMatch(controlRoutine(routine, editor.candidate_policy), editor.config) && <p role="status" className="text-ember-deep">The routine above differs from this experiment. Use it explicitly to update the saved assumptions.</p>}
            <Button variant="secondary" onClick={() => change('config', controlRoutine(routine, editor.candidate_policy))}>Use current routine</Button>
            <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Inspect experiment routine</summary><pre className="max-h-64 overflow-auto text-caption">{JSON.stringify(editor.config, null, 2)}</pre></details>
            <section aria-label="Experiment criteria editor" className="space-y-3"><h3 className="font-semibold">Success criteria</h3><p className="text-caption text-ink-secondary">Choose bounds for candidate outcomes. Blank bounds are unset. Day targets need a reached-rate target to protect children who never reach the reward; rates use 0 to 1 and money uses cents.</p>
              {editor.targets.map((row, index) => { const metric = metadata.feedback.metrics.find((entry) => entry.key === row.metric); return <div key={index} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end rounded-lg bg-ink-page-aged p-3"><SelectField label={`Criterion ${index + 1} measure`} value={row.metric} onChange={(event) => target(index, 'metric', event.target.value)}>{metadata.feedback.metrics.filter((entry) => entry.key === row.metric || !editor.targets.some((other) => other.metric === entry.key)).map((entry) => <option key={entry.key} value={entry.key}>{entry.label} ({entry.unit})</option>)}</SelectField>{['min', 'max'].map((key) => <TextField key={key} label={`Criterion ${index + 1} ${key === 'min' ? 'minimum' : 'maximum'}`} type="number" step="any" min={metric?.min_value} max={metric?.max_value} value={row[key]} onChange={(event) => target(index, key, event.target.value === '' ? '' : Number(event.target.value))} />)}<Button variant="ghost" onClick={() => change('targets', editor.targets.filter((_, position) => position !== index))}>Remove criterion {index + 1}</Button></div>; })}
              <Button variant="secondary" disabled={editor.targets.length >= metadata.feedback.max_targets} onClick={() => { const metric = metadata.feedback.metrics.find((entry) => !editor.targets.some((row) => row.metric === entry.key)); if (metric) change('targets', [...editor.targets, { metric: metric.key, min: '', max: '' }]); }}>Add criterion</Button>
            </section>
          </fieldset>
          <div className="flex flex-wrap gap-3"><Button type="submit" disabled={busy}>Save experiment</Button>{saved && <Button variant="secondary" disabled={busy || dirty} onClick={compare}>{busy ? 'Working…' : 'Run control and candidate'}</Button>}</div>
          {dirty && saved && <p role="status" className="text-ember-deep">Experiment inputs have changed. Save them before running or deciding.</p>}
        </form>
        <ErrorAlert message={error} />
        {notice && <p role="status">{notice}</p>}
        {saved && <>
          <SelectField label="Saved comparison" value={comparison?.id ?? ''} disabled={busy} onChange={(event) => openComparison(event.target.value)}><option value="">Choose saved evidence</option>{saved.comparisons.map((row) => <option key={row.id} value={row.id}>Revision {row.experiment_revision} · {row.created_at}{row.stale ? ' · stale' : ''}</option>)}</SelectField>
          {comparison && <ExperimentComparison comparison={comparison} dirty={dirty} />}
          <section aria-label="Observation checkpoints" className="space-y-3"><h3 className="font-semibold">Observation checkpoints</h3><p className="text-caption text-ink-secondary">Save the server's current bounded family ledger evidence for later comparison. An empty checkpoint records insufficient evidence; it cannot validate a policy.</p><Button variant="secondary" disabled={busy || dirty} onClick={() => run((options) => saveProgressionObservation(saved.id, { revision: saved.revision }, options), (data) => { remember(data); setNotice('Observation checkpoint saved. This is evidence of the installed economy.'); })}>Save observation checkpoint</Button>{(saved.observations ?? []).map((row) => <details key={row.id}><summary className="min-h-11 cursor-pointer py-3 font-semibold">Checkpoint {row.created_at} · {row.status.replaceAll('_', ' ')}</summary><p className="text-caption text-ink-secondary">Saved experiment revision {row.experiment_revision}. No live experiment is implied.</p><ProgressionObservations observations={row.payload} /><pre className="max-h-40 overflow-auto text-caption">{JSON.stringify(row.binding, null, 2)}</pre></details>)}</section>
          <form aria-label="Record experiment decision" onSubmit={recordDecision} className="space-y-3">
            <SectionHeader as="h3" title="Decision and next action">Record a dated design decision against current saved evidence. Ready for design requires configured, passing criteria; it never approves deployment or publication.</SectionHeader>
            <fieldset disabled={busy || !canDecide} className="min-w-0 space-y-3"><legend className="sr-only">Decision details</legend><SelectField label="Decision" value={decision.outcome} onChange={(event) => setDecision((previous) => ({ ...previous, outcome: event.target.value }))}>{Object.entries(decisionLabels).map(([key, label]) => <option key={key} value={key} disabled={key === 'ready_for_design' && comparison?.evaluation.status !== 'pass'}>{label}</option>)}</SelectField><TextAreaField label="Decision reason" value={decision.rationale} maxLength={2000} required onChange={(event) => setDecision((previous) => ({ ...previous, rationale: event.target.value }))} /><TextAreaField label="Next action" value={decision.next_action} maxLength={2000} required onChange={(event) => setDecision((previous) => ({ ...previous, next_action: event.target.value }))} /><TextField label="Review on" type="date" required value={decision.review_on} onChange={(event) => setDecision((previous) => ({ ...previous, review_on: event.target.value }))} /></fieldset>
            <Button type="submit" disabled={busy || !canDecide || (decision.outcome === 'ready_for_design' && comparison?.evaluation.status !== 'pass')}>Record decision</Button>
          </form>
          {saved.decisions.length > 0 && <section aria-label="Recorded experiment decisions" className="space-y-2"><h3 className="font-semibold">Recorded decisions</h3><ul className="space-y-3">{saved.decisions.map((row) => <li key={row.id} className="rounded-lg bg-ink-page-aged p-3"><strong>{decisionLabels[row.outcome]}</strong><p>{row.rationale}</p><p>{row.next_action}</p><p className="text-caption text-ink-secondary">Review on {row.review_on} · evidence {row.comparison_id}</p></li>)}</ul></section>}
        </>}
        <RewardProposal proposal={metadata.feedback.proposal} />
      </>}
    </ParchmentCard>
    <ErrorAlert message={observationError} onRetry={readObservations} />
    <Button variant="secondary" disabled={observationLoading} onClick={readObservations}>Refresh observed evidence</Button>
    <ProgressionObservations observations={observations} loading={observationLoading} />
    {confirmation && <ConfirmDialog title={confirmation.discardEditor ? "Discard unsaved experiment changes?" : "Discard unsaved decision notes?"} message={confirmation.discardEditor ? "Your saved experiment and evidence remain available. Unsaved experiment or decision notes will be discarded." : "This action replaces the evidence for this decision. Your unsaved decision notes will be discarded; experiment inputs will be kept."} confirmLabel="Discard changes" onCancel={() => setConfirmation(null)} onConfirm={() => { const action = confirmation.action; if (confirmation.discardEditor) setEditor(saved ? fields(saved) : freshEditor(routine)); setDecision(blankDecision); setConfirmation(null); action(); }} />}
  </section>;
}
