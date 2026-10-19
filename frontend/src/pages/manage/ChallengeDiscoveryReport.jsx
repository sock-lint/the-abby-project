import { useEffect, useState } from 'react';
import { getChallengeDiscovery } from '../../api';
import { getToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import ParchmentCard from '../../components/journal/ParchmentCard';
import SectionHeader from '../../components/SectionHeader';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';

const number = (value) => Number.isFinite(value) ? new Intl.NumberFormat().format(value) : 'Unavailable';

export default function ChallengeDiscoveryReport() {
  const { user } = useAuth();
  const token = getToken();
  if (!user?.id || user.role !== 'parent') return null;
  return <FamilyDiscoveryReport key={`${user.id}:${user.family?.id ?? ''}:${token}`} token={token} />;
}

function FamilyDiscoveryReport({ token }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    getChallengeDiscovery({ signal: controller.signal }).then((response) => {
      if (active && token === getToken()) { setData(response); setError(null); }
    }).catch((failure) => {
      if (active && token === getToken() && failure.name !== 'AbortError') setError(failure.message);
    }).finally(() => {
      if (active && token === getToken()) setLoading(false);
    });
    return () => { active = false; controller.abort(); };
  }, [revision, token]);
  const refresh = () => { setLoading(true); setRevision((value) => value + 1); };
  const available = data?.status === 'observations_available';
  const counts = data?.catalog_occurrences;
  return <ParchmentCard as="section" aria-label="Recorded challenge discovery" className="space-y-3">
    <SectionHeader title="Recorded challenge discovery">Compare challenge openings with completions for new children in your family.</SectionHeader>
    <p className="text-caption text-ink-secondary">These are recorded app actions, separate from simulations. Opening details does not establish that a child read or enjoyed them.</p>
    {loading && <p role="status">Loading challenge discovery…</p>}
    <ErrorAlert message={error} onRetry={refresh} />
    {data && <>
      <p className="text-caption text-ink-secondary">{data.period.since} through {data.period.until} · {data.period.timezone}. One-time catalog windows created during this period for accounts registered within {data.cohort.registered_within_days} days.</p>
      {!available ? <p role="status">{data.status === 'insufficient_evidence'
        ? 'No tracked challenge windows in this new-user cohort yet.'
        : 'Observation capacity was exceeded. Counts are unavailable; no partial sample is shown.'}</p> : <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          ['Challenge windows created', counts.cohort_materialized], ['Details opened', counts.opened],
          ['Completed', counts.completed], ['Completed without a recorded opening', counts.completed_without_recorded_opening],
        ].map(([label, value]) => <div key={label}><dt className="text-caption text-ink-secondary">{label}</dt><dd className="text-lede font-semibold">{number(value)}</dd></div>)}
      </dl>}
      <p className="text-caption text-ink-secondary">Windows created by the server are not screen impressions. Older accounts without tracking remain unknown; an absent opening is not proof that someone never saw a challenge.</p>
      {available && counts.cohort_materialized > counts.opened && <p className="text-body text-ink-secondary">Some tracked windows have no recorded details opening. Review how children find them before adding more content to this path.</p>}
      <details>
        <summary className="min-h-11 py-3 cursor-pointer font-semibold">Discovery coverage and accounting</summary>
        <p className="text-caption text-ink-secondary">{number(data.cohort.tracked_children)} tracked children · {number(data.cohort.untracked_children)} with unknown earlier opening history.</p>
        {available && <p className="text-caption text-ink-secondary">{number(counts.opened_and_completed)} windows both opened and completed. {number(counts.opening_recorded_after_completion)} first openings were recorded after completion. These groups overlap the totals above.</p>}
        <ul className="list-disc pl-5 space-y-2 text-caption text-ink-secondary">{data.notes.map((note) => <li key={note}>{note}</li>)}</ul>
      </details>
    </>}
    <Button variant="secondary" disabled={loading} onClick={refresh}>Refresh discovery</Button>
  </ParchmentCard>;
}
