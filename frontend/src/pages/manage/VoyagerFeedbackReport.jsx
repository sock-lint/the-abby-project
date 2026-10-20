import { useEffect, useState } from 'react';
import { getVoyagerFeedback } from '../../api';
import { getToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import ParchmentCard from '../../components/journal/ParchmentCard';
import SectionHeader from '../../components/SectionHeader';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';

const number = (value) => Number.isFinite(value) ? new Intl.NumberFormat().format(value) : 'Unknown';
const percent = (value) => Number.isFinite(value)
  ? new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 }).format(value) : 'Unavailable';
const unavailable = {
  insufficient_evidence: 'No eligible new children in this family yet. There is not enough evidence to evaluate Voyager.',
  catalog_unavailable: 'Reading Voyager could not be identified in the current catalog. Counts are unknown.',
  catalog_ambiguous: 'More than one Reading Voyager definition matches. Counts are unknown until the catalog identity is resolved.',
  cohort_limit_exceeded: 'The new-child cohort exceeds this report’s capacity. Counts are unavailable; no partial sample is shown.',
  record_limit_exceeded: 'Saved records exceed this report’s capacity. Counts are unavailable; no partial sample is shown.',
};

export default function VoyagerFeedbackReport() {
  const { user } = useAuth();
  const token = getToken();
  if (!user?.id || user.role !== 'parent' || !user.is_staff) return null;
  return <FamilyVoyagerFeedback key={`${user.id}:${user.family?.id ?? ''}:${token}`} token={token} />;
}

function FamilyVoyagerFeedback({ token }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    getVoyagerFeedback({ signal: controller.signal }).then((response) => {
      if (active && token === getToken()) { setData(response); setError(null); }
    }).catch((failure) => {
      if (active && token === getToken() && failure.name !== 'AbortError') setError(failure.message);
    }).finally(() => {
      if (active && token === getToken()) setLoading(false);
    });
    return () => { active = false; controller.abort(); };
  }, [revision, token]);
  const refresh = () => { if (!loading) { setLoading(true); setRevision((value) => value + 1); } };
  const available = data?.status === 'observations_available';
  const counts = data?.current_states;
  const nextReading = data?.catalog?.acceptance_mode === 'next_qualifying_reading';
  return <ParchmentCard as="section" aria-label="Reading Voyager feedback" className="space-y-3">
    <SectionHeader title="Reading Voyager feedback">Follow new children’s Voyager progress using saved app records.</SectionHeader>
    <p className="text-caption text-ink-secondary">This is a snapshot of children in your family, separate from anonymous simulations. It does not measure global retention or when a child first became eligible.</p>
    {loading && <p role="status">{data ? 'Refreshing Voyager feedback…' : 'Loading Voyager feedback…'}</p>}
    <ErrorAlert message={error && `Voyager feedback could not be refreshed. ${error}`} onRetry={refresh} />
    {data && <>
      {error && <p role="status" className="text-ember-deep">Last successful snapshot shown below. The refresh failed; these counts may have changed.</p>}
      {data.period && <p className="text-caption text-ink-secondary">Snapshot recorded: {data.period.as_of} · {data.period.timezone}. Accounts registered within {data.cohort?.registered_within_days} days ({data.period.since} through {data.period.until}); all their saved Voyager windows are included.</p>}
      {!available ? <p role="status">{unavailable[data.status] ?? 'The Voyager report is unavailable. Counts are unknown; refresh to try again.'}</p> : <>
        <p className="text-body text-ink-secondary">{number(data.cohort.eligible_children)} new children in this family’s cohort.</p>
        <h3 className="font-semibold">Current child states</h3>
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[
            ['Locked', counts.locked], [nextReading ? 'Ready for next Reading Adventure' : 'Available for automatic tracking', counts.ready],
            ['Window active', counts.active], ['Completed', counts.completed], ['Expired', counts.expired], ['State unknown', counts.unknown],
          ].map(([label, value]) => <div key={label}><dt className="text-caption text-ink-secondary">{label}</dt><dd className="text-lede font-semibold">{number(value)}</dd></div>)}
        </dl>
        <p className="text-caption text-ink-secondary">These states describe each child now. They are not a history of gate transitions.{nextReading && ' Ready children start their window on their next new qualifying daily Reading Adventure.'}</p>
        <h3 className="font-semibold">Saved policy outcomes</h3>
        {data.policy_groups.length > 0 ? <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Saved Voyager policies, horizontally scrollable">
          <table className="w-full text-left text-body">
            <caption className="sr-only">Voyager outcomes by saved policy</caption>
            <thead><tr>{['Saved policy', 'Windows started', 'Still observing', 'Mature completed', 'Mature expired', 'Mature unresolved', 'Mature completion', 'Unknown timing'].map((label) => <th key={label} scope="col" className="p-2 align-top">{label}</th>)}</tr></thead>
            <tbody>{data.policy_groups.map((group) => <tr key={group.policy} className="border-t border-ink-whisper/20">
              <th scope="row" className="p-2 align-top min-w-48">{group.label}</th>
              {[group.accepted_windows, group.pending_windows, group.mature_completed, group.mature_expired, group.mature_unknown].map((value, index) => <td key={index} className="p-2 align-top">{number(value)}</td>)}
              <td className="p-2 align-top min-w-40">{group.completion_rate == null && group.mature_denominator === 0 ? 'No resolved mature outcomes' : percent(group.completion_rate)}<span className="block text-caption text-ink-secondary">{number(group.mature_completed)} of {number(group.mature_denominator)} resolved mature windows</span></td>
              <td className="p-2 align-top">{number(group.unknown_windows)}</td>
            </tr>)}</tbody>
          </table>
        </div> : <p className="text-body text-ink-secondary">No saved Voyager windows are recorded for this cohort.</p>}
        <p className="text-caption text-ink-secondary">Mature completion uses completed plus expired windows whose full saved deadline has passed. Still observing includes early completions before that deadline. Windows still within their deadline are not counted as failures. Unresolved outcomes and unknown timing are excluded from the rate.</p>
        <p className="text-caption text-ink-secondary">Policies come from saved promises. Older 45-day windows, the selected 56-day milestones and other or unknown policies stay separate; today’s catalog does not rewrite history.</p>
      </>}
      <details>
        <summary className="min-h-11 py-3 cursor-pointer font-semibold">Voyager coverage and accounting</summary>
        <ul className="list-disc pl-5 space-y-2 text-caption text-ink-secondary">{(data.notes ?? []).map((note) => <li key={note}>{note}</li>)}</ul>
      </details>
    </>}
    <Button variant="secondary" disabled={loading} onClick={refresh}>Refresh Voyager feedback</Button>
  </ParchmentCard>;
}
