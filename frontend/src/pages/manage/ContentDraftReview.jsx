import { Link } from 'react-router-dom';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import ParchmentCard from '../../components/journal/ParchmentCard';
import SectionHeader from '../../components/SectionHeader';
import { CheckboxField, SelectField, TextField } from '../../components/form';

const names = {
  horizon_days: 'Forecast horizon in days', trials: 'Simulated children', seed: 'Random seed',
  active_days_per_week: 'Active days per week', reading_minutes: 'Reading minutes per active day',
  project_minutes: 'Project minutes per active day', chores_per_day: 'Approved chores per active day',
  chore_coins: 'Coins per approved chore', chore_xp: 'XP per approved chore',
  habits_per_day: 'Habit logs per active day', habit_xp: 'XP per habit log',
  movement_sessions_per_day: 'Movement sessions per active day', movement_minutes: 'Minutes per movement session',
  movement_intensity: 'Movement intensity', creations_per_day: 'Creations per active day',
  journal_per_day: 'One journal entry per active day', feed_strategy: 'Feeding strategy',
  expeditions_per_day: 'Expeditions per active day', expedition_tier: 'Expedition length',
};
const number = (value) => Number.isFinite(value) ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value) : 'Unavailable';
const day = (value) => value == null ? 'Not reached' : `Day ${number(value)}`;
const display = (value) => value == null ? 'None' : typeof value === 'object' ? JSON.stringify(value) : String(value);

export function AuditFindings({ audit, title = 'Reward audit' }) {
  const findings = Array.isArray(audit) ? audit : audit?.findings ?? [];
  return <section aria-label={title} className="space-y-3">
    <h3 className="font-semibold text-ink-primary">{title}</h3>
    {audit?.incomplete && <p role="status" className="text-ember-deep">This audit is incomplete. Review the reported limits before publishing.</p>}
    {findings.length ? <ul className="space-y-2">{findings.map((finding, index) => <li key={`${finding.code}:${index}`} className="rounded-lg bg-ink-page-aged p-3 text-body break-words"><strong>{finding.severity}: </strong>{finding.detail ?? finding.message}<span className="block text-caption text-ink-secondary">{finding.code}{finding.section ? ` · ${finding.section}` : ''}{finding.id ? ` · ${finding.id}` : ''}</span></li>)}</ul> : <p className="text-body text-ink-secondary">No findings reported for the checked definitions. Excluded systems remain outside this audit.</p>}
  </section>;
}

export default function ContentDraftReview({ draft, preview, simulation, metadata, config, onConfig, onPreview, onSimulate, onPublish, busy, dirty, error }) {
  const published = Boolean(draft.published_at);
  const boundSimulation = simulation?.preview_id === preview?.preview_id && simulation?.revision === draft.revision;
  const safePreview = Boolean(preview && !dirty && !published);
  const field = (key) => {
    const value = config[key];
    const limit = metadata?.limits?.[key] ?? {};
    const label = names[key] ?? key.replaceAll('_', ' ');
    if (typeof value === 'boolean') return <CheckboxField key={key} label={label} checked={value} onChange={(event) => onConfig({ ...config, [key]: event.target.checked })} />;
    if (limit.choices) return <SelectField key={key} label={label} value={String(value)} onChange={(event) => onConfig({ ...config, [key]: typeof value === 'number' ? Number(event.target.value) : event.target.value })}>{limit.choices.map((choice) => <option key={choice} value={choice}>{String(choice).replaceAll('_', ' ')}</option>)}</SelectField>;
    return <TextField key={key} label={label} type="number" required min={limit.min} max={limit.max} step="1" value={value} onChange={(event) => onConfig({ ...config, [key]: event.target.value === '' ? '' : Number(event.target.value) })} />;
  };
  return <ParchmentCard className="space-y-4">
    <SectionHeader title="Review, audit and compare" index={2}>Publication changes the shared catalog. Existing saved ownership and accepted reward promises remain preserved.</SectionHeader>
    <p role="status" className="text-body text-ink-secondary">{published ? 'Published' : `Draft revision ${draft.revision}`} · {draft.changes.length} saved {draft.changes.length === 1 ? 'entry' : 'entries'}{dirty ? ' · Save or discard your editor changes before reviewing.' : ''}</p>
    <ErrorAlert message={error} />
    {!published && <Button variant="secondary" onClick={onPreview} disabled={busy || dirty || !draft.changes.length}>Preview changes and audit rewards</Button>}
    {preview && <>
      <section aria-label="Exact publication preview" className="space-y-3">
        <h3 className="font-semibold text-ink-primary">Changes in this preview</h3>
        <p className="text-caption text-ink-secondary">{preview.expires_at ? `Review expires ${new Date(preview.expires_at).toLocaleString()}. ` : ''}If the draft or published catalog changes, create a fresh preview and comparison.</p>
        {!preview.changes?.length && <p>No catalog changes in this preview.</p>}
        <ul className="space-y-2">{(preview.changes ?? []).map((change, index) => <li key={`${change.object}:${index}`} className="rounded-lg border border-ink-whisper/20 p-3 break-words">
          <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">{change.action}: {change.after?.name ?? change.before?.name ?? change.object}</summary>
            <dl className="space-y-2">{[...new Set([...Object.keys(change.before ?? {}), ...Object.keys(change.after ?? {})])].filter((key) => JSON.stringify(change.before?.[key]) !== JSON.stringify(change.after?.[key])).map((key) => <div key={key}><dt className="font-semibold capitalize">{key.replaceAll('_', ' ')}</dt><dd className="text-caption text-ink-secondary">Before: {display(change.before?.[key])}</dd><dd className="text-caption text-ink-primary">After: {display(change.after?.[key])}</dd></div>)}</dl>
          </details>
        </li>)}</ul>
      </section>
      <AuditFindings audit={preview.audits} />
      {safePreview && config && <form aria-label="Draft comparison scenario" onSubmit={(event) => { event.preventDefault(); onSimulate(); }} className="space-y-4">
        <SectionHeader as="h3" title="Simulate published content against this draft">Both forecasts use the same routine, seed and rules. Simulations use anonymous state and never create children or award rewards.</SectionHeader>
        <fieldset disabled={busy} className="min-w-0 space-y-3"><legend className="sr-only">Comparison assumptions</legend>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">{['horizon_days', 'trials', 'seed'].filter((key) => key in config).map(field)}</div>
          <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Edit activity and reward assumptions</summary>
            {metadata.presets?.length > 0 && <div className="flex flex-wrap gap-2 py-3">{metadata.presets.map((preset) => <Button key={preset.name} variant="secondary" onClick={() => onConfig({ ...preset.config })}>Use {preset.name.toLowerCase()} routine</Button>)}</div>}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">{Object.keys(config).filter((key) => !['horizon_days', 'trials', 'seed'].includes(key)).map(field)}</div>
          </details>
        </fieldset>
        <Button type="submit" disabled={busy}>{busy ? 'Working…' : 'Compare published and draft'}</Button>
      </form>}
      {boundSimulation && <Comparison simulation={simulation} config={config} />}
      {safePreview && <div className="space-y-2"><Button onClick={onPublish} disabled={busy || !boundSimulation || preview.audits?.incomplete || preview.audits?.findings?.some((finding) => finding.severity === 'error')}>Publish reviewed draft</Button><p className="text-caption text-ink-secondary">Review the exact changes, audit findings and completed comparison first. Publication asks for an explicit confirmation.</p></div>}
    </>}
    <Link to="/manage/progression-lab" className="inline-flex min-h-11 items-center text-sheikah-teal-deep underline font-semibold">Open progression lab for a deeper scenario</Link>
  </ParchmentCard>;
}

function Comparison({ simulation, config }) {
  const { baseline, proposed } = simulation;
  if (!baseline || !proposed) return null;
  const changed = JSON.stringify(config) !== JSON.stringify(proposed.config);
  const end = (report, key) => report.trace?.at(-1)?.[key];
  const metrics = [
    ['Modeled finite targets', (report) => report.summary.finite_content_total],
    ['Targets not completed at horizon (median)', (report) => report.summary.finite_remaining_p50],
    ['Longest discovery gap (median days)', (report) => report.summary.longest_novelty_gap_p50],
    ['Expired unfinished challenges (median)', (report) => report.summary.expired_oneoff_challenges_p50],
    ['Coins saved at horizon (median)', (report) => end(report, 'coins_p50')],
    ['Total XP at horizon (median)', (report) => end(report, 'total_xp_p50')],
  ];
  const coverage = proposed.coverage;
  return <section aria-label="Published and draft comparison" className="space-y-4">
    <SectionHeader as="h3" title="Published versus draft">{proposed.config.trials} simulated children · {proposed.config.horizon_days} days · seed {proposed.config.seed}. Forecasts describe this model and routine; discovery gaps do not measure boredom.</SectionHeader>
    {changed && <p role="status" className="text-ember-deep">Scenario inputs have changed. This comparison still shows the last completed routine.</p>}
    <div className="overflow-x-auto"><table className="w-full text-left text-body"><caption className="sr-only">Published and proposed content forecast</caption><thead><tr><th className="p-2">Measure</th><th className="p-2">Published</th><th className="p-2">Draft</th><th className="p-2">Difference</th></tr></thead><tbody>{metrics.map(([label, read]) => {
      const before = read(baseline); const after = read(proposed);
      return <tr key={label} className="border-t border-ink-whisper/20"><th scope="row" className="p-2 font-semibold">{label}</th><td className="p-2">{number(before)}</td><td className="p-2">{number(after)}</td><td className="p-2">{Number.isFinite(before) && Number.isFinite(after) ? number(after - before) : 'Unavailable'}</td></tr>;
    })}</tbody></table></div>
    <p className="text-caption text-ink-secondary">Finite targets cover only modeled eligible badges, one-time challenges, cosmetics and companion stages. Expired challenges remain uncompleted and do not represent future runway. A draft can change the total target count.</p>
    <div className="overflow-x-auto"><table className="w-full text-left text-body"><caption className="font-semibold text-left py-2">Milestone completion and timing</caption><thead><tr><th className="p-2">Milestone</th><th className="p-2">Published completion</th><th className="p-2">Published median day</th><th className="p-2">Draft completion</th><th className="p-2">Draft median day</th></tr></thead><tbody>{(proposed.milestones ?? []).map((entry) => {
      const original = baseline.milestones?.find((milestone) => milestone.key === entry.key);
      return <tr key={entry.key} className="border-t border-ink-whisper/20"><th scope="row" className="p-2 font-semibold">{entry.label}</th><td className="p-2">{original ? `${number(original.completion_rate * 100)}%` : 'Unavailable'}</td><td className="p-2">{day(original?.p50_days)}</td><td className="p-2">{number(entry.completion_rate * 100)}%</td><td className="p-2">{day(entry.p50_days)}</td></tr>;
    })}</tbody></table></div>
    <p className="text-caption text-ink-secondary">Completion rates include every simulated child; median days include only children who reached the milestone.</p>
    {coverage?.excluded?.length > 0 && <section className="space-y-2" aria-label="Excluded from this forecast"><h4 className="font-semibold">Excluded from this forecast</h4><ul className="list-disc pl-5 text-body text-ink-secondary">{coverage.excluded.map((entry, index) => <li key={index}>{typeof entry === 'string' ? entry : JSON.stringify(entry)}</li>)}</ul></section>}
    <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Comparison identity</summary><dl className="space-y-2 break-all text-caption text-ink-secondary"><div><dt>Model version</dt><dd>{proposed.engine_version ?? 'Unavailable'}</dd></div><div><dt>Published rules fingerprint</dt><dd>{baseline.rules_fingerprint ?? 'Unavailable'}</dd></div><div><dt>Draft rules fingerprint</dt><dd>{proposed.rules_fingerprint ?? 'Unavailable'}</dd></div><div><dt>Published catalog fingerprint</dt><dd>{baseline.catalog?.fingerprint ?? 'Unavailable'}</dd></div><div><dt>Draft catalog fingerprint</dt><dd>{proposed.catalog?.fingerprint ?? 'Unavailable'}</dd></div></dl></details>
    <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Model coverage and reward flows</summary><div className="space-y-3">
      {coverage && ['modeled', 'assumptions'].map((key) => <div key={key}><h4 className="font-semibold capitalize">{key}</h4><ul className="list-disc pl-5 text-body text-ink-secondary">{(coverage[key] ?? []).map((entry, index) => <li key={index}>{typeof entry === 'string' ? entry : JSON.stringify(entry)}</li>)}</ul></div>)}
      {['baseline', 'proposed'].map((key) => <div key={key}><h4 className="font-semibold">{key === 'baseline' ? 'Published' : 'Draft'} reward sources · mean per child</h4><ul className="text-body text-ink-secondary">{(simulation[key].flows?.sources ?? []).map((entry) => <li key={entry.source}>{entry.source.replaceAll('_', ' ')}: {number(entry.coins)} coins, {number(entry.xp)} XP, {number(entry.items)} items</li>)}</ul></div>)}
    </div></details>
  </section>;
}
