import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { getProgressionLab, simulateProgressionLab } from '../../api';
import { getToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';
import PageShell from '../../components/layout/PageShell';
import PageHeader from '../../components/layout/PageHeader';
import SectionHeader from '../../components/SectionHeader';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import AttachmentField from '../../components/attachments/AttachmentField';
import { CheckboxField, SelectField, TextField } from '../../components/form';
import ProgressionEconomyControls from './ProgressionEconomyControls';
import ProgressionEconomyReport from './ProgressionEconomyReport';
import ProgressionRewardBudgetControls from './ProgressionRewardBudgetControls';
import ProgressionRewardBudgetReport from './ProgressionRewardBudgetReport';
import ProgressionCommitmentControls from './ProgressionCommitmentControls';
import ProgressionCommitmentReport from './ProgressionCommitmentReport';
import ProgressionExpeditionBudgetControls from './ProgressionExpeditionBudgetControls';
import ProgressionExpeditionBudgetReport from './ProgressionExpeditionBudgetReport';
import ProgressionExperimentNotebook from './ProgressionExperimentNotebook';
import { expeditionBudgetLabel, importedScenario, rewardPolicyLabel, scenariosMatch } from './progressionLabScenario';
import PetIncubationPolicy from './PetIncubationPolicy';
import PetIncubationState from './PetIncubationState';
import PetIncubationJourney from './PetIncubationJourney';
import ChallengeDiscoveryReport from './ChallengeDiscoveryReport';

const ROUTINE_FIELDS = [
  ['active_days_per_week', 'Active days per week', 'Visits occur on the first N days of each repeating week.'],
  ['reading_minutes', 'Reading minutes per active day'],
  ['project_minutes', 'Project minutes per active day'],
  ['chores_per_day', 'Approved chores per active day'],
  ['habits_per_day', 'Habit logs per active day'],
  ['movement_sessions_per_day', 'Movement sessions per active day'],
  ['movement_minutes', 'Minutes per movement session'],
  ['creations_per_day', 'Creations per active day'],
];
const REWARD_FIELDS = [
  ['chore_coins', 'Coins per approved chore'],
  ['chore_xp', 'XP per approved chore'],
  ['habit_xp', 'XP per habit log'],
  ['expeditions_per_day', 'Expeditions per active day'],
];
const OPTION_LABELS = {
  low: 'Low', medium: 'Medium', high: 'High',
  feed_all: 'Feed available food', none: 'Do not feed',
  short: 'Short (2 hours)', standard: 'Standard (4 hours)', long: 'Long (8 hours)',
};
const number = (value) => Number.isFinite(value) ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value) : 'Unavailable';
const milestoneDay = (value) => value == null ? 'Not reached' : `Day ${number(value)}`;

export default function ProgressionLab() {
  const { user } = useAuth();
  if (!user?.id) return <Loader />;
  if (user.role !== 'parent') return <PageShell><PageHeader title="Progression lab" /><p>Progression lab is available to staff parents.</p></PageShell>;
  return <AccountProgressionLab key={`${user.id}:${user.role}:${user.family?.id ?? ''}:${getToken()}`} />;
}

function AccountProgressionLab() {
  const [metadata, setMetadata] = useState(null);
  const [loading, setLoading] = useState(true);
  const [readError, setReadError] = useState(null);
  const [denied, setDenied] = useState(false);
  const [revision, setRevision] = useState(0);
  const [config, setConfig] = useState(null);
  const [result, setResult] = useState(null);
  const [resultInputs, setResultInputs] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [savedFile, setSavedFile] = useState(null);
  const [importError, setImportError] = useState(null);
  const [importBusy, setImportBusy] = useState(false);
  const [imported, setImported] = useState(false);
  const importSequence = useRef(0);
  const active = useRef(false);
  const request = useRef(null);
  const token = getToken();
  const dirty = Boolean(config && metadata && !scenariosMatch(config, metadata.defaults));
  usePwaUpdateGuard(dirty || busy || importBusy);

  useEffect(() => {
    active.current = true;
    return () => { active.current = false; request.current?.abort(); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let alive = true;
    getProgressionLab({ signal: controller.signal })
      .then((data) => {
        if (!alive || token !== getToken()) return;
        setMetadata(data);
        setConfig((previous) => previous ?? data.defaults);
        setReadError(null);
      })
      .catch((error) => {
        if (!alive || token !== getToken() || error.name === 'AbortError') return;
        if (error.status === 401 || error.status === 403) setDenied(true);
        else setReadError(error.message);
      })
      .finally(() => { if (alive && token === getToken()) setLoading(false); });
    return () => { alive = false; controller.abort(); };
  }, [revision, token]);

  const change = (key, value) => {
    setConfig((previous) => ({ ...previous, [key]: value }));
    setFieldErrors((previous) => ({ ...previous, [key]: null }));
  };
  const retryRead = () => { setLoading(true); setReadError(null); setRevision((value) => value + 1); };
  const importRoutine = async (file) => {
    const sequence = ++importSequence.current;
    setSavedFile(file);
    setImportError(null);
    setImported(false);
    setImportBusy(Boolean(file));
    if (!file) return;
    try {
      const importedConfig = await readSavedRoutine(file, metadata);
      if (!active.current || token !== getToken() || sequence !== importSequence.current) return;
      setConfig(importedConfig);
      setFieldErrors({});
      setRunError(null);
      setImported(true);
    } catch (error) {
      if (active.current && token === getToken() && sequence === importSequence.current) setImportError(`${error.message} Your current inputs have been kept.`);
    } finally {
      if (active.current && token === getToken() && sequence === importSequence.current) setImportBusy(false);
    }
  };
  const simulate = async (event) => {
    event.preventDefault();
    if (busy || importBusy) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setRunError(null);
    setFieldErrors({});
    const submitted = JSON.parse(JSON.stringify(config));
    try {
      const response = await simulateProgressionLab(submitted, { signal: controller.signal });
      if (active.current && token === getToken()) { setResult(response); setResultInputs(submitted); }
    } catch (error) {
      if (!active.current || token !== getToken() || error.name === 'AbortError') return;
      if (error.status === 401 || error.status === 403) {
        setDenied(true);
      } else if (error.status === 400 && error.response && typeof error.response === 'object') {
        setFieldErrors(Object.fromEntries(Object.entries(error.response).map(([key, value]) => [key, Array.isArray(value) ? value.join(' ') : String(value)])));
        setRunError(error.response.detail || error.response.error || 'Check the scenario fields and run again. Your inputs have been kept.');
      } else setRunError(`The simulation could not finish. Your inputs have been kept. ${error.message}`);
    } finally {
      if (active.current && token === getToken()) setBusy(false);
    }
  };

  return (
    <PageShell rhythm="loose">
      <PageHeader title="Progression lab" kicker="Designer workspace · new children starting from zero" />
      <Link to="/manage?tab=Admin" className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep underline">Back to administration</Link>
      <Link to="/manage/rpg-content" className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep underline">Manage challenges and items</Link>
      {denied ? <p role="status">Progression lab is available to staff parents.</p> : <>
        <p className="text-body text-ink-secondary">Explore what a child can earn and discover through an ordinary routine. These are design forecasts, not measured player behavior or a prediction of when a child becomes bored.</p>
        <ErrorAlert message={readError && `Could not load the rules and catalog. ${readError}`} onRetry={retryRead} />
        {loading && <Loader />}
        {metadata && config && <>
          <ChallengeDiscoveryReport />
          <ParchmentCard className="space-y-4">
            <SectionHeader title="Build a new child’s routine" index={0}>All activity counts apply to active days. Scenarios use anonymous state and do not create accounts or change rewards.</SectionHeader>
            <form aria-label="Progression scenario" onSubmit={simulate} className="space-y-4">
              <fieldset disabled={busy || importBusy} className="space-y-4 min-w-0">
                <legend className="sr-only">Scenario assumptions</legend>
                <details>
                  <summary className="min-h-11 py-3 cursor-pointer font-semibold text-ink-primary">Load a saved routine</summary>
                  <AttachmentField label="Saved routine" chooseLabel="Load saved routine" file={savedFile} onChange={importRoutine} accept="application/json,.json" disabled={busy || importBusy} error={importError} helpText="Choose an exported JSON report up to 1 MB. Only its routine is read on this device. Review it and run a fresh simulation with the current rules; saved results are never restored as current facts." />
                  {imported && <p role="status" className="text-body text-ink-secondary">Saved routine loaded. Review the inputs, then run a fresh simulation using the current rules.</p>}
                </details>
                {metadata.presets?.length > 0 && <div className="space-y-2">
                  <p className="text-caption text-ink-secondary">Starting routines are editable examples, not observed player groups.</p>
                  <div className="flex flex-wrap gap-2">{metadata.presets.map((preset) => <Button key={preset.name} type="button" variant="secondary" onClick={() => { setConfig((previous) => ({ ...preset.config, ...(previous.economy ? { economy: previous.economy } : {}), ...(previous.reward_budget ? { reward_budget: previous.reward_budget } : {}), ...(previous.reward_commitment ? { reward_commitment: previous.reward_commitment } : {}), ...(previous.expedition_budget ? { expedition_budget: previous.expedition_budget } : {}) })); setFieldErrors({}); }}>Use {preset.name.toLowerCase()} routine</Button>)}</div>
                  {(config.economy || config.reward_budget) && <p className="text-caption text-ink-secondary">Routine presets keep your purchasing, Coin policy and expedition limits.</p>}
                </div>}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <ChoiceField name="horizon_days" label="Forecast horizon" config={config} limits={metadata.limits} onChange={change} errors={fieldErrors} />
                  <NumericField name="trials" label="Simulated children" config={config} limits={metadata.limits} onChange={change} errors={fieldErrors} help="Longer or busier routines and additional reward offers may need fewer simulated children. Requests over the model budget are rejected; counts are never silently reduced." />
                  <NumericField name="seed" label="Random seed" config={config} limits={metadata.limits} onChange={change} errors={fieldErrors} help="Use the same seed to reproduce a report." />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  {ROUTINE_FIELDS.map(([name, label, help]) => <NumericField key={name} name={name} label={label} help={help} config={config} limits={metadata.limits} onChange={change} errors={fieldErrors} />)}
                  <ChoiceField name="movement_intensity" label="Movement intensity" config={config} limits={metadata.limits} onChange={change} errors={fieldErrors} />
                  <CheckboxField label="One journal entry per active day" checked={config.journal_per_day} onChange={(event) => change('journal_per_day', event.target.checked)} />
                </div>
                <details>
                  <summary className="min-h-11 cursor-pointer font-semibold text-ink-primary py-3">Reward and companion assumptions</summary>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-3">
                    {REWARD_FIELDS.map(([name, label]) => <NumericField key={name} name={name} label={label} config={config} limits={metadata.limits} onChange={change} errors={fieldErrors} />)}
                    <ChoiceField name="feed_strategy" label="Feeding strategy" config={config} limits={metadata.limits} onChange={change} errors={fieldErrors} />
                    <ChoiceField name="expedition_tier" label="Expedition length" config={config} limits={metadata.limits} onChange={change} errors={fieldErrors} />
                  </div>
                  <p className="text-caption text-ink-secondary mt-3">These values change this scenario only. Parent approvals are assumed complete. See model coverage below for the exact companion and reward behavior included.</p>
                  <PetIncubationPolicy policy={metadata.pet_incubation_policy} context="metadata" />
                </details>
                {metadata.reward_budget_defaults && metadata.reward_budget_limits && <ProgressionRewardBudgetControls budget={config.reward_budget ?? metadata.reward_budget_defaults}
                  limits={metadata.reward_budget_limits} onChange={(budget) => setConfig((previous) => ({ ...previous, reward_budget: budget, ...(budget.daily_coins != null ? { reward_commitment: { enabled: false } } : {}) }))} error={fieldErrors.reward_budget ?? fieldErrors['reward_budget.daily_coins']} />}
                {metadata.reward_commitment_defaults && <ProgressionCommitmentControls commitment={config.reward_commitment ?? metadata.reward_commitment_defaults}
                  onChange={(commitment) => setConfig((previous) => ({ ...previous, reward_commitment: commitment, ...(commitment.enabled ? { reward_budget: { daily_coins: null } } : {}) }))} error={fieldErrors.reward_commitment ?? fieldErrors['reward_commitment.enabled']} />}
                {metadata.expedition_budget_defaults && metadata.expedition_budget_limits && <ProgressionExpeditionBudgetControls budget={config.expedition_budget ?? metadata.expedition_budget_defaults} limits={metadata.expedition_budget_limits} onChange={(budget) => change('expedition_budget', budget)} errors={fieldErrors} />}
                {metadata.economy_defaults && metadata.economy_limits && <ProgressionEconomyControls economy={config.economy ?? metadata.economy_defaults} metadata={metadata}
                  onChange={(economy) => change('economy', economy)}
                  onExample={() => {
                    const economy = JSON.parse(JSON.stringify(metadata.economy_defaults));
                    economy.enabled = true;
                    economy.offers = [{ ...metadata.economy_offer_defaults, key: 'example-outing', label: 'Example outing', coin_price: 100, repeat_every_days: 7, family_cost_cents: 500 }];
                    setConfig((previous) => ({ ...previous, horizon_days: 90, trials: 10, economy }));
                    setFieldErrors({});
                  }} />}
              </fieldset>
              <ErrorAlert message={runError} />
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit" disabled={busy || importBusy}>{busy ? 'Running simulation…' : 'Run simulation'}</Button>
                <span role="status" className="text-caption text-ink-secondary">{busy ? 'Calculating anonymous journeys…' : 'No household records are used.'}</span>
              </div>
            </form>
          </ParchmentCard>
          {result && <>
            {!scenariosMatch(config, resultInputs ?? result.config) && <p role="status" className="text-body text-ember-deep">Inputs have changed. The report below still shows the last completed scenario.</p>}
            <Report key={`${result.config.seed}:${result.config.horizon_days}:${result.config.trials}`} report={result} baseline={baseline} onBaseline={() => setBaseline(result)} onClearBaseline={() => setBaseline(null)} />
          </>}
          <ProgressionExperimentNotebook routine={config} />
          <Coverage coverage={(result ?? metadata).coverage} audit={(result ?? metadata).audit} catalog={(result ?? metadata).catalog} />
        </>}
      </>}
    </PageShell>
  );
}

async function readSavedRoutine(file, metadata) {
  if (file.size > 1_000_000) throw new Error('Choose a JSON report no larger than 1 MB.');
  const text = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('The selected file could not be read.'));
    reader.readAsText(file);
  });
  let saved;
  try { saved = JSON.parse(text); } catch { throw new Error('Choose a valid JSON report.'); }
  return importedScenario(saved, metadata);
}

function NumericField({ name, label, help, config, limits, onChange, errors }) {
  return <TextField label={label} type="number" min={limits[name]?.min} max={limits[name]?.max} step="1" required value={config[name]} onChange={(event) => onChange(name, event.target.value === '' ? '' : Number(event.target.value))} helpText={help} error={errors[name]} />;
}

function ChoiceField({ name, label, config, limits, onChange, errors }) {
  return <SelectField label={label} value={String(config[name])} onChange={(event) => onChange(name, typeof config[name] === 'number' ? Number(event.target.value) : event.target.value)} error={errors[name]}>
    {(limits[name]?.choices ?? []).map((value) => <option key={value} value={value}>{name === 'horizon_days' ? `${value} calendar days` : OPTION_LABELS[value] ?? value}</option>)}
  </SelectField>;
}

function Report({ report, baseline, onBaseline, onClearBaseline }) {
  const [index, setIndex] = useState(0);
  const snapshots = report.trace ?? [];
  const snapshot = snapshots[index];
  const versionsMatch = baseline && baseline.engine_version && report.engine_version
    && [baseline.rules_fingerprint, report.rules_fingerprint, baseline.catalog.fingerprint, report.catalog.fingerprint].every((value) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value))
    && baseline.engine_version === report.engine_version && baseline.rules_fingerprint === report.rules_fingerprint
    && baseline.catalog.fingerprint === report.catalog.fingerprint;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `abby-progression-${report.config.seed}-${report.config.horizon_days}d.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return <section aria-label="Simulation report" className="space-y-4">
    <SectionHeader title="Your progression forecast" index={1} actions={<><Button variant="secondary" onClick={onBaseline}>Keep as comparison</Button><Button variant="secondary" onClick={download}>Download JSON report</Button></>}>
      {report.config.trials} simulated children · {report.config.horizon_days} calendar days · seed {report.config.seed}. Ranges describe this model and routine only.
    </SectionHeader>
    {baseline && <div className="flex flex-wrap items-center gap-3 text-body text-ink-secondary" role="status">Comparing with {baseline.config.horizon_days} days, {baseline.config.trials} children, seed {baseline.config.seed}, {number(baseline.summary.finite_content_total)} finite targets. Changing activities can change that denominator.<Button variant="ghost" onClick={onClearBaseline}>Clear comparison</Button></div>}
    {baseline && !versionsMatch && <p role="status" className="text-body text-ember-deep">Comparison versions: unavailable or different. Numeric differences may include changes to the model, rules or catalog. Treat these as separate forecasts.</p>}
    {baseline && <p className="text-caption text-ink-secondary">Purchasing is {report.economy?.enabled ? 'on' : 'off'} in this report and {baseline.economy?.enabled ? 'on' : 'off'} in the comparison. {!scenariosMatch(report.config.economy, baseline.config.economy) && 'Purchasing assumptions differ; review their offers, budgets and earned-money assumptions alongside the totals.'}</p>}
    {baseline && (report.reward_budget || baseline.reward_budget) && <p className="text-caption text-ink-secondary">Reward policy: {rewardPolicyLabel(report.config)} in this report; {rewardPolicyLabel(baseline.config)} in the comparison.</p>}
    {baseline && <p className="text-caption text-ink-secondary">Expedition limits: {expeditionBudgetLabel(report.config.expedition_budget)} in this report; {expeditionBudgetLabel(baseline.config.expedition_budget)} in the comparison.</p>}
    <PetIncubationPolicy policy={report.pet_incubation_policy} />
    <ParchmentCard className="space-y-3">
      <SectionHeader as="h3" title="Modeled runway at a glance">Finite targets include eligible modeled badges, one-time challenges, obtainable cosmetics and companion stages. They describe a subset of Abby’s content, not total app exhaustion.</SectionHeader>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[['Finite targets in this scenario', report.summary.finite_content_total], ['Targets not completed at horizon (median)', report.summary.finite_remaining_p50], ['Active days in the horizon', report.summary.active_days], ['Longest discovery gap (median days)', report.summary.longest_novelty_gap_p50], ['Expired unfinished one-time challenges (median)', report.summary.expired_oneoff_challenges_p50]].map(([label, value]) => <div key={label}><dt className="text-caption text-ink-secondary">{label}</dt><dd className="text-lede font-semibold text-ink-primary">{number(value)}</dd></div>)}
      </dl>
      <p className="text-caption text-ink-secondary">Uncompleted targets include expired one-time challenges. Check expired counts and audit findings before treating this count as future content.</p>
      {report.summary.expired_oneoff_challenges_p50 > 0 && <p role="status" className="text-body text-ember-deep">Some one-time challenges expired unfinished in the median journey. Those missed targets remain uncompleted and do not provide future runway in this model.</p>}
      <p className="text-caption text-ink-secondary">Discovery gaps count calendar days without a new modeled finite target, including the opening and ending gaps in the forecast. They do not measure boredom.</p>
      {report.summary.finite_breakdown && <div className="space-y-2 text-caption text-ink-secondary">
        <p>{Object.entries(report.summary.finite_breakdown).map(([key, value]) => `${number(value)} ${({ badge: 'badges', quest: 'one-time challenges', cosmetic: 'cosmetics', pet: 'hatched stages', middle: 'middle stages', mount: 'grown stages' })[key] ?? key}`).join(' · ')}</p>
        <p>Hatched, middle and grown are three milestones for the same companion, not three different companions.</p>
      </div>}
      {report.summary.finite_content_total === 0 && <p className="text-body text-ember-deep">No finite targets belong to this scenario’s modeled source subset. This does not mean the app has no content.</p>}
    </ParchmentCard>
    <ParchmentCard className="space-y-3">
      <SectionHeader as="h3" title="When milestones happen">The completion rate uses all simulated children. Day ranges use only children who reached that milestone; “Not reached” means none did within the horizon.</SectionHeader>
      <div className="overflow-x-auto">
        <table className="w-full text-body text-left">
          <caption className="sr-only">Milestone completion and calendar days among successful journeys</caption>
          <thead><tr className="border-b border-ink-whisper/20"><th className="p-2">Milestone</th><th className="p-2">Reached</th><th className="p-2">Earlier (10%)</th><th className="p-2">Median</th><th className="p-2">Later (90%)</th>{baseline && <th className="p-2">Comparison median</th>}</tr></thead>
          <tbody>{report.milestones.map((milestone) => <tr key={milestone.key} className="border-b border-ink-whisper/20"><th scope="row" className="p-2 font-semibold">{milestone.label}</th><td className="p-2">{number(milestone.completion_rate * 100)}%{milestone.completed_trials != null && <span className="block text-caption text-ink-secondary">{milestone.completed_trials} / {milestone.trials} children</span>}</td><td className="p-2 whitespace-nowrap">{milestoneDay(milestone.p10_days)}</td><td className="p-2 whitespace-nowrap">{milestoneDay(milestone.p50_days)}</td><td className="p-2 whitespace-nowrap">{milestoneDay(milestone.p90_days)}</td>{baseline && <td className="p-2 whitespace-nowrap">{milestoneDay(baseline.milestones.find((entry) => entry.key === milestone.key)?.p50_days)}</td>}</tr>)}</tbody>
        </table>
      </div>
    </ParchmentCard>
    <ParchmentCard className="space-y-3">
      <SectionHeader as="h3" title="Discovery and uncompleted targets">The curve counts uncompleted modeled targets, including expired challenges. Each value below is the median across all simulated children, not one child’s exact journey.</SectionHeader>
      {snapshot ? <>
        <RunwayChart rows={snapshots} />
        <TextField label="Inspect calendar day" type="range" min="0" max={snapshots.length - 1} step="1" value={index} onChange={(event) => setIndex(Number(event.target.value))} helpText={`Day ${snapshot.day}`} />
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3" aria-label={`Day ${snapshot.day} median state`}>
          {[['Discovered', snapshot.finite_completed_p50], ['Modeled targets not completed', snapshot.finite_remaining_p50], [report.economy?.enabled ? 'Coins available' : 'Coins saved', snapshot.coins_p50], ['Total XP', snapshot.total_xp_p50], ['Character level', snapshot.level_p50], ['Inventory units held', snapshot.inventory_units_p50], ['Hatched companions', snapshot.pets_p50], ['Grown companions', snapshot.mounts_p50], ['Expired unfinished challenges', snapshot.expired_oneoff_challenges_p50]].map(([label, value]) => <div key={label} className="rounded-lg bg-ink-page-aged p-3"><dt className="text-caption text-ink-secondary">{label}</dt><dd className="text-lede font-semibold text-ink-primary">{number(value)}</dd></div>)}
        </dl>
        <PetIncubationState snapshot={snapshot} />
      </> : <p>No timeline is available for this report.</p>}
    </ParchmentCard>
    <ParchmentCard className="space-y-3">
      <SectionHeader as="h3" title="Reward sources and consumption">Mean totals per child across all {report.config.trials} simulated children and {report.config.horizon_days} calendar days. {report.economy?.enabled ? 'This report includes only the anonymous reward offers and purchasing assumptions below. Live household shops are not read.' : 'Coins remain savings in this model. Household shops, real-world rewards and purchasing decisions are excluded; this is not a spending forecast.'}</SectionHeader>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4"><FlowTable title="Sources" rows={report.flows?.sources ?? []} /><FlowTable title="Sinks and consumption" rows={report.flows?.sinks ?? []} /></div>
    </ParchmentCard>
    {!report.reward_commitment?.enabled && <ProgressionRewardBudgetReport budget={report.reward_budget} baseline={baseline?.reward_commitment?.enabled ? null : baseline?.reward_budget} />}
    <ProgressionCommitmentReport commitment={report.reward_commitment} />
    <ProgressionExpeditionBudgetReport budget={report.expedition_budget} baseline={baseline?.expedition_budget} />
    <ProgressionEconomyReport economy={report.economy} baseline={baseline?.economy} config={report.config.economy} />
    <ParchmentCard className="space-y-3">
      <SectionHeader as="h3" title="Inspect a reproducible journey">Representative trial seed: {report.journey?.seed ?? report.config.seed}. This event log describes one child; the summaries above describe the whole group.</SectionHeader>
      <PetIncubationJourney events={report.journey?.events} policy={report.pet_incubation_policy} truncated={report.journey?.truncated} />
      <details><summary className="min-h-11 py-3 cursor-pointer font-semibold text-ink-primary">Show event receipts</summary>
        <pre className="max-h-96 overflow-auto rounded-lg bg-ink-page-aged p-3 text-caption">{JSON.stringify(report.journey?.events ?? [], null, 2)}</pre>
        {report.journey?.truncated && <p className="text-caption text-ink-secondary">The event preview is bounded. The report marks it as truncated.</p>}
      </details>
      <details><summary className="min-h-11 py-3 cursor-pointer font-semibold text-ink-primary">Show exact scenario and model summary</summary><pre className="max-h-96 overflow-auto rounded-lg bg-ink-page-aged p-3 text-caption">{JSON.stringify({ config: report.config, summary: report.summary, pet_incubation_policy: report.pet_incubation_policy, engine_version: report.engine_version, source_commit: report.source_commit, rules_fingerprint: report.rules_fingerprint, catalog_fingerprint: report.catalog.fingerprint }, null, 2)}</pre></details>
    </ParchmentCard>
  </section>;
}

function RunwayChart({ rows }) {
  const finiteRows = rows.filter((row) => Number.isFinite(row.finite_remaining_p50));
  if (!finiteRows.length) return <p>No finite-content measurements are available.</p>;
  const maxDay = Math.max(...finiteRows.map((row) => row.day), 1);
  const measuredMaximum = Math.max(...finiteRows.map((row) => row.finite_remaining_p50));
  const scaleMaximum = Math.max(measuredMaximum, 1);
  const points = finiteRows.map((row) => `${32 + row.day / maxDay * 536},${140 - row.finite_remaining_p50 / scaleMaximum * 112}`).join(' ');
  return <figure className="space-y-2">
    <svg role="img" aria-label="Median modeled targets not completed over calendar days" viewBox="0 0 600 170" className="w-full text-sheikah-teal-deep">
      <line x1="32" y1="140" x2="568" y2="140" stroke="currentColor" opacity="0.3" />
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" />
      <text x="32" y="162" fill="currentColor" fontSize="12">Day 0</text><text x="568" y="162" textAnchor="end" fill="currentColor" fontSize="12">Day {maxDay}</text>
      <text x="32" y="17" fill="currentColor" fontSize="12">{number(measuredMaximum)} finite targets</text>
    </svg>
    <figcaption className="text-caption text-ink-secondary">Median modeled targets not completed; expired challenges remain in this count. Inspect a sampled day below.</figcaption>
  </figure>;
}

function FlowTable({ title, rows }) {
  return <div className="space-y-2"><h4 className="font-semibold text-ink-primary">{title}</h4>{rows.length ? <div className="overflow-x-auto"><table className="w-full text-body text-left"><caption className="sr-only">{title}: mean totals per simulated child</caption><thead><tr><th className="p-2">Activity</th><th className="p-2">Coins</th><th className="p-2">XP</th><th className="p-2">Items</th></tr></thead><tbody>{rows.map((row) => <tr key={row.source} className="border-t border-ink-whisper/20"><th scope="row" className="p-2 font-semibold capitalize">{row.source.replaceAll('_', ' ')}</th><td className="p-2">{number(row.coins)}</td><td className="p-2">{number(row.xp)}</td><td className="p-2">{number(row.items)}</td></tr>)}</tbody></table></div> : <p className="text-body text-ink-secondary">No modeled entries.</p>}</div>;
}

function Coverage({ coverage, audit, catalog }) {
  return <ParchmentCard className="space-y-4">
    <SectionHeader title="Model coverage and audit" index={2}>A forecast is only as complete as its model. Exclusions and catalog findings remain visible alongside every result.</SectionHeader>
    <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      {[['Supported companion pairs', catalog.supported_pet_variants], ['Supported items', catalog.supported_items], ['Modeled badge definitions', catalog.modeled_badges], ['Excluded badge definitions', catalog.excluded_badges], ['One-time challenge definitions', catalog.nonrepeatable_challenges], ['System challenge definitions', catalog.system_challenges]].map(([label, value]) => <div key={label}><dt className="text-caption text-ink-secondary">{label}</dt><dd className="font-semibold text-ink-primary">{number(value)}</dd></div>)}
    </dl>
    <p className="text-caption text-ink-secondary">These are loaded global definitions. A scenario’s enabled activities and obtainable rewards determine its own finite-target denominator.</p>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">{[['modeled', 'Included'], ['excluded', 'Excluded'], ['assumptions', 'Assumptions']].map(([key, label]) => <section key={key} className="space-y-2"><h3 className="font-semibold text-ink-primary">{label}</h3><ul className="list-disc pl-5 space-y-2 text-body text-ink-secondary">{(coverage?.[key] ?? []).map((entry, index) => <li key={index}>{typeof entry === 'string' ? entry : JSON.stringify(entry)}</li>)}</ul></section>)}</div>
    {coverage.activity_skills && <details><summary className="min-h-11 py-3 cursor-pointer font-semibold text-ink-primary">Inspect activity skill assumptions</summary><div className="space-y-2 text-body text-ink-secondary">{Object.entries(coverage.activity_skills).map(([source, tags]) => <p key={source}><strong className="capitalize">{source}: </strong>{tags.map(([category, skill, weight]) => `${category} / ${skill} (weight ${weight})`).join(', ')}</p>)}</div></details>}
    <section className="space-y-2"><h3 className="font-semibold text-ink-primary">Audit findings</h3>{audit?.length ? <ul className="space-y-2">{audit.map((finding, index) => <li key={`${finding.code}:${index}`} className="rounded-lg bg-ink-page-aged p-3 text-body"><span className="font-semibold">{finding.severity}: </span>{finding.message}<span className="block text-caption text-ink-secondary">{finding.code}</span></li>)}</ul> : <p className="text-body text-ink-secondary">No findings reported by this audit. This does not establish that excluded systems have been checked.</p>}</section>
    <details><summary className="min-h-11 py-3 cursor-pointer font-semibold text-ink-primary">Inspect catalog and finite-content denominator</summary><pre className="max-h-96 overflow-auto rounded-lg bg-ink-page-aged p-3 text-caption">{JSON.stringify(catalog, null, 2)}</pre></details>
  </ParchmentCard>;
}
