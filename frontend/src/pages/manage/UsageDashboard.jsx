import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getUsageDashboard } from '../../api';
import { getToken } from '../../api/client';
import useUsageSession from '../../hooks/useUsageSession';
import PageShell from '../../components/layout/PageShell';
import PageHeader from '../../components/layout/PageHeader';
import SectionHeader from '../../components/SectionHeader';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import { SelectField } from '../../components/form';

const FEATURES = {
  all: 'All features', homework: 'Homework', chores: 'Chores', projects: 'Projects',
  reading: 'Reading', movement: 'Movement', habits: 'Habits', rewards: 'Rewards',
};
const METRICS = [
  ['active_families', 'Active families'], ['active_children', 'Active children'],
  ['active_parents', 'Active parents'], ['completed_activities', 'Activities recorded'],
];
const number = (value) => Number.isFinite(value) ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value) : 'Unavailable';
const percent = (value) => Number.isFinite(value) ? new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 }).format(value) : 'Unavailable';
const date = (value) => value ? value.slice(0, 10) : 'Unavailable';

export default function UsageDashboard() {
  const { user, token, key } = useUsageSession();
  if (!user?.id || !token) return <Loader />;
  if (user.role !== 'parent') return <PageShell><PageHeader title="Usage" /><p role="status">Usage is available to staff parents.</p></PageShell>;
  return <AccountUsageDashboard key={key} token={token} />;
}

function AccountUsageDashboard({ token }) {
  const [filters, setFilters] = useState({ scope: 'family', days: 28, role: 'all', feature: 'all' });
  const [canViewDeployment, setCanViewDeployment] = useState(false);
  const receiveCapability = useCallback((allowed) => setCanViewDeployment(allowed === true), []);
  const change = (name, value) => setFilters((previous) => ({ ...previous, [name]: value }));
  return <PageShell rhythm="loose">
    <PageHeader title="Usage" kicker="Meaningful activity and returning families" />
    <Link to="/manage?tab=Admin" className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep underline">Back to administration</Link>
    <p className="text-body text-ink-secondary">An active person has a saved, meaningful action. Visits are counted separately. Background polling and reward side effects do not count as engagement.</p>
    <ParchmentCard as="section" aria-label="Usage filters" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      <SelectField label="Scope" value={filters.scope} onChange={(event) => change('scope', event.target.value)}>
        <option value="family">My family</option>
        {canViewDeployment && <option value="deployment">All families</option>}
      </SelectField>
      <SelectField label="Date range" value={filters.days} onChange={(event) => change('days', Number(event.target.value))}>
        <option value={7}>Last 7 days</option><option value={28}>Last 28 days</option><option value={90}>Last 90 days</option>
      </SelectField>
      <SelectField label="Role" value={filters.role} onChange={(event) => change('role', event.target.value)}>
        <option value="all">Parents and children</option><option value="parent">Parents</option><option value="child">Children</option>
      </SelectField>
      <SelectField label="Feature" value={filters.feature} onChange={(event) => change('feature', event.target.value)}>
        {Object.entries(FEATURES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </SelectField>
    </ParchmentCard>
    <UsageReport key={JSON.stringify(filters)} filters={filters} token={token} onCapability={receiveCapability} />
  </PageShell>;
}

function UsageReport({ filters, token, onCapability }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [denied, setDenied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    getUsageDashboard(filters, { signal: controller.signal, token }).then((response) => {
      if (!active || token !== getToken()) return;
      if (response.scope !== filters.scope || Object.entries(response.filters ?? {}).some(([key, value]) => String(value) !== String(filters[key]))) {
        throw new Error('The report did not match the selected filters. Try again.');
      }
      setData(response);
      setError(null);
      onCapability(response.can_view_deployment);
    }).catch((failure) => {
      if (!active || token !== getToken() || failure.name === 'AbortError') return;
      if ([401, 403].includes(failure.status)) {
        setDenied(true);
        setData(null);
        onCapability(false);
      } else setError(failure.message);
    }).finally(() => { if (active && token === getToken()) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [filters, token, revision, onCapability]);
  const refresh = () => { if (!loading) { setLoading(true); setRevision((value) => value + 1); } };
  if (denied) return <p role="status">Usage is available to staff parents. Viewing all families also requires deployment administrator access.</p>;
  return <div className="space-y-4" aria-label="Usage report" aria-busy={loading}>
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="secondary" disabled={loading} onClick={refresh}>Refresh usage</Button>
      {loading && <p role="status">{data ? 'Refreshing usage…' : 'Loading usage…'}</p>}
    </div>
    <ErrorAlert message={error && `Usage could not be loaded. ${error}`} onRetry={refresh} />
    {data && <>
      {error && <p role="status" className="text-ember-deep">Last successful snapshot shown below. The refresh failed; these counts may have changed.</p>}
      <p className="text-caption text-ink-secondary">{data.scope === 'deployment' ? 'All families' : 'My family'} · {date(data.period.start)} through {date(data.period.end)} · UTC</p>
      {!data.collection.history_complete && <p role="status" className="text-body text-ink-secondary">{data.collection.started_at ? `Partial history: collection began ${date(data.collection.started_at)}.` : 'Collection is starting.'} Earlier activity and incomplete observation windows are unavailable.</p>}
      {data.summary.current.actions === 0 && <EmptyState>No meaningful activity recorded for these filters. Missing history is not evidence that nobody used Abby.</EmptyState>}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {METRICS.map(([key, label]) => <ParchmentCard key={key}>
          <dl><dt className="text-body text-ink-secondary">{label}</dt><dd className="text-3xl font-bold text-ink-primary mt-2">{number(data.summary.current[key])}</dd></dl>
          <p className="text-caption text-ink-secondary mt-2">Previous period: {data.collection.previous_history_complete ? number(data.summary.previous[key]) : 'Collecting history'}</p>
        </ParchmentCard>)}
      </div>
      <p className="text-caption text-ink-secondary">Activities recorded means work submitted or logged, before any required parent approval. Meaningful actions include approvals and reward requests. Visits: {number(data.summary.current.visitors)} unique people; meaningful actions: {number(data.summary.current.actions)}. Feature filters do not change visit counts. Previous period: {date(data.period.previous_start)} through {date(data.period.previous_end)}.</p>
      <UsageTrend rows={data.trend} startedAt={data.collection.started_at} />
      <ParchmentCard as="section" aria-label="Feature adoption" className="space-y-3">
        <SectionHeader title="Feature adoption">Unique people and saved actions within the selected dates, role and feature.</SectionHeader>
        <Table caption="Feature adoption" headings={['Feature', 'People', 'Actions', 'Activities recorded']}>
          {data.features.map((row) => <tr key={row.feature}><th scope="row" className="p-2">{FEATURES[row.feature] ?? row.feature}</th>{[row.actors, row.actions, row.completed_activities].map((value, index) => <td className="p-2" key={index}>{number(value)}</td>)}</tr>)}
        </Table>
      </ParchmentCard>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ParchmentCard as="section" aria-label="Getting started" className="space-y-3">
          <SectionHeader title="Getting started">Families created in the selected dates and their progress through the report end. Role and feature filters do not apply.</SectionHeader>
          <dl className="space-y-2">{[['families_created', 'Family created'], ['child_added', 'Child added'], ['first_activity', 'First activity submitted or logged'], ['first_parent_approval', 'First observed parent approval']].map(([key, label]) => <div className="flex justify-between gap-3" key={key}><dt>{label}</dt><dd className="font-semibold">{number(data.onboarding[key])}</dd></div>)}</dl>
          <p className="text-caption text-ink-secondary">{data.onboarding.coverage}</p>
        </ParchmentCard>
        <ParchmentCard as="section" aria-label="Returning families" className="space-y-3">
          <SectionHeader title="Returning families">Whole-family meaningful activity in completed calendar weeks, independent of date-range, role and feature filters.</SectionHeader>
          {[['week_1', 'Families active one week earlier'], ['week_4', 'Families active four weeks earlier']].map(([key, label]) => {
            const cohort = data.retention[key];
            return <div key={key}><h3 className="font-semibold">{label}</h3><p>{!cohort.history_complete ? 'Collecting history' : cohort.rate == null ? (cohort.eligible_families === 0 ? 'No active families in the earlier week' : 'Rate unavailable') : percent(cohort.rate)}</p>{cohort.history_complete && <p className="text-caption text-ink-secondary">{number(cohort.returned_families)} returned of {number(cohort.eligible_families)} eligible families</p>}<p className="text-caption text-ink-secondary">Active {date(cohort.cohort_start)} through {date(cohort.cohort_end)}; returning {date(cohort.return_start)} through {date(cohort.return_end)}.</p></div>;
          })}
          <p className="text-caption text-ink-secondary">{data.retention.definition}</p>
        </ParchmentCard>
      </div>
      <ParchmentCard as="section" aria-label="Review queue and friction" className="space-y-3">
        <SectionHeader title="Review queue and friction">Current review queue for {data.friction.coverage.map((key) => FEATURES[key] ?? key).join(' and ')}. Dates and role do not filter the current queue; feature does.</SectionHeader>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div><dt>Awaiting parent review</dt><dd className="text-2xl font-semibold">{number(data.friction.pending_reviews)}</dd></div>
          <div><dt>Median approval time</dt><dd className="text-2xl font-semibold">{data.friction.median_approval_hours == null ? 'Unavailable' : `${number(data.friction.median_approval_hours)} hours`}</dd></div>
        </dl>
        <p className="text-caption text-ink-secondary">Approval time uses recorded decisions within the selected dates, role and feature. Missing timing is unavailable, never zero.</p>
        <p className="text-caption text-ink-secondary">Workflow abandonment, failed saves, sign-in failures and request latency are not measured in this dashboard. Use the existing Sentry monitoring for errors.</p>
        <a href="https://logs.neato.digital" target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep underline">Open error monitoring</a>
      </ParchmentCard>
      <ParchmentCard as="section" aria-label="Weekly summary" className="space-y-3">
        <SectionHeader title="Weekly summary">Last seven UTC days including today: {date(data.weekly_summary.start)} through {date(data.weekly_summary.end)}. Role and feature filters apply to actions; visits have no feature filter. The selected date range does not apply.</SectionHeader>
        <p className="text-body">{number(data.weekly_summary.active_families)} active families, {number(data.weekly_summary.active_children)} children and {number(data.weekly_summary.active_parents)} parents recorded {number(data.weekly_summary.completed_activities)} activities and {number(data.weekly_summary.actions)} meaningful actions. {number(data.weekly_summary.visitors)} people visited.</p>
      </ParchmentCard>
      <ParchmentCard as="section" aria-label="Coverage and privacy" className="space-y-3">
        <SectionHeader title="Coverage and privacy" />
        <p className="text-body text-ink-secondary">This report contains aggregate counts. Usage telemetry excludes journal content, form text, raw page URLs and session recordings. Designated live-check households are excluded. Usage telemetry is retained for {number(data.collection.retention_days)} days.</p>
        <ul className="list-disc pl-5 space-y-2 text-caption text-ink-secondary">{data.collection.notes.map((note) => <li key={note}>{note}</li>)}</ul>
      </ParchmentCard>
    </>}
  </div>;
}

function Table({ caption, headings, children }) {
  return <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={`${caption}, horizontally scrollable`}>
    <table className="w-full text-left text-body"><caption className="sr-only">{caption}</caption><thead><tr>{headings.map((heading) => <th key={heading} scope="col" className="p-2">{heading}</th>)}</tr></thead><tbody className="divide-y divide-ink-whisper/20">{children}</tbody></table>
  </div>;
}

function UsageTrend({ rows, startedAt }) {
  const [granularity, setGranularity] = useState('daily');
  const firstObservedDate = startedAt ? date(startedAt) : null;
  const partialFirstDay = startedAt && new Date(startedAt).toISOString().slice(11) !== '00:00:00.000Z';
  const buckets = new Map();
  for (const row of rows) {
    const day = new Date(`${row.date}T00:00:00Z`);
    if (granularity === 'weekly') day.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 6) % 7));
    const label = day.toISOString().slice(0, 10);
    const bucket = buckets.get(label) ?? { count: 0, observed: false, partial: false };
    if (firstObservedDate && row.date >= firstObservedDate) {
      bucket.count += row.completed_activities;
      bucket.observed = true;
      if (row.date === firstObservedDate && partialFirstDay) bucket.partial = true;
    } else bucket.partial = true;
    buckets.set(label, bucket);
  }
  const entries = [...buckets.entries()].sort(([left], [right]) => left.localeCompare(right));
  const maximum = Math.max(1, ...entries.map(([, bucket]) => bucket.count));
  const plotted = entries.flatMap(([, bucket], index) => bucket.observed ? [{ x: 20 + (index / Math.max(1, entries.length - 1)) * 560, y: 140 - (bucket.count / maximum) * 120 }] : []);
  const points = plotted.map(({ x, y }) => `${x},${y}`).join(' ');
  return <ParchmentCard as="section" aria-label="Activity trend" className="space-y-3">
    <SectionHeader title="Activity trend" actions={<SelectField label="Trend interval" value={granularity} onChange={(event) => setGranularity(event.target.value)} variant="filter"><option value="daily">Daily</option><option value="weekly">Weekly</option></SelectField>}>Activities submitted or logged; a weekly bucket includes only selected dates.</SectionHeader>
    {plotted.length > 0 ? <>
    <p className="text-caption text-ink-secondary">Activities recorded · scale: 0 to {number(maximum)}</p>
    <svg viewBox="0 0 600 160" className="w-full h-40 text-sheikah-teal-deep" role="img" aria-label={`Activities recorded by ${granularity === 'daily' ? 'day' : 'week'}, scale 0 to ${number(maximum)}; exact counts in the table below`}>
      <line x1="20" y1="140" x2="580" y2="140" stroke="currentColor" opacity="0.3" />
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" />
      {plotted.length === 1 && <circle cx={plotted[0].x} cy={plotted[0].y} r="4" fill="currentColor" />}
    </svg>
    <div className="flex flex-wrap justify-between gap-2 text-caption text-ink-secondary" aria-label="Trend date range"><span>{entries[0][0]}</span><span>{entries.at(-1)[0]}</span></div>
    </> : <p role="status">Collecting history — no observed trend dates yet.</p>}
    <p className="text-caption text-ink-secondary">Dates before collection began are unavailable. The first collection day and any week containing missing dates have partial history. Today is still in progress.</p>
    <details><summary className="min-h-11 py-3 cursor-pointer font-semibold">View exact trend counts</summary>
      <Table caption="Activity trend counts" headings={[granularity === 'daily' ? 'Date (UTC)' : 'Week beginning (UTC)', 'Activities recorded']}>
        {entries.map(([label, bucket]) => <tr key={label}><th className="p-2" scope="row">{label}</th><td className="p-2">{bucket.observed ? `${number(bucket.count)}${bucket.partial ? ' (partial history)' : ''}` : 'Unavailable'}</td></tr>)}
      </Table>
    </details>
  </ParchmentCard>;
}
