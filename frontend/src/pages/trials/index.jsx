import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getChildren, pinChallenge, unpinChallenge } from '../../api';
import { getToken } from '../../api/client';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import useChallenges, { CHALLENGES_CHANGED } from '../../hooks/useChallenges';
import { normalizeList } from '../../utils/api';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';
import PageHeader from '../../components/layout/PageHeader';
import SectionHeader from '../../components/SectionHeader';
import EmptyState from '../../components/EmptyState';
import { SelectField } from '../../components/form';
import DailyChallengeCard from '../../components/dashboard/DailyChallengeCard';
import CreateGoalForm from './CreateGoalForm';
import ChallengeGoalCard, { ChallengeGoalDetail } from './ChallengeGoalCard';

export default function Trials() {
  const { user, isParent } = useRole();
  const [searchParams] = useSearchParams();
  const [childId, setChildId] = useState('');
  const { data: childrenData, error: childrenError, reload: reloadChildren } = useApi(
    async () => ({ owner: user?.id, children: isParent ? await getChildren() : [] }), [isParent, user?.id],
  );
  const children = useMemo(() => childrenData?.owner === user?.id ? normalizeList(childrenData?.children) : [], [childrenData, user?.id]);
  const targetChild = isParent ? childId || children[0]?.id : undefined;
  const { data, goals, pinnedGoal, loading, error, reload, setData } = useChallenges({ userId: targetChild });
  const [selectedId, setSelectedId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const identity = `${user?.id}:${getToken()}`;
  const identityRef = useRef(identity);
  useEffect(() => { identityRef.current = identity; }, [identity]);
  const selected = goals.find((goal) => goal.id === (selectedId ?? searchParams.get('goal')));
  const timezone = data?.daily_bonus?.timezone || data?.timezone || 'UTC';
  const active = goals.filter((goal) => goal.status === 'active' && goal.id !== pinnedGoal?.id);
  const upcoming = goals.filter((goal) => goal.status === 'upcoming');
  const history = goals.filter((goal) => goal.status !== 'active' && goal.status !== 'upcoming');

  const handlePin = async (goal) => {
    const requestIdentity = identity;
    setBusy(true);
    setActionError('');
    try {
      const response = goal.pinned ? await unpinChallenge(goal.id) : await pinChallenge(goal.id);
      if (requestIdentity !== identityRef.current) return;
      setData((previous) => ({ ...previous, pin: response.pin, results: previous.results.map((row) => ({ ...row, pinned: row.id === response.pin })) }));
      window.dispatchEvent(new Event(CHALLENGES_CHANGED));
    } catch (err) {
      if (requestIdentity === identityRef.current) setActionError(err.message);
    } finally {
      if (requestIdentity === identityRef.current) setBusy(false);
    }
  };
  const handleCreated = (created, assigneeId) => {
    if (!created) {
      reload();
      return;
    }
    setSelectedId(created.id);
    if (String(assigneeId) !== String(targetChild)) setChildId(String(assigneeId));
    else reload();
  };
  if (loading || !user) return <Loader />;
  const cardProps = { timezone, onSelect: (goal) => setSelectedId(goal.id), onPin: isParent ? undefined : handlePin, busy, canAct: !isParent };
  return (
    <div className="space-y-5">
      <PageHeader title="Challenges" kicker="Complete tasks to make progress" />
      <p className="font-body text-body text-ink-secondary max-w-xl">Challenges are optional goals that add bonus rewards to the tasks you already do. Every matching goal progresses automatically. Pin one to keep it on Today.</p>
      {searchParams.has('scroll') && <p className="font-body text-caption text-ink-secondary">You can track challenges without spending a scroll. Your saved scroll stays in Inventory.</p>}
      {isParent && <div className="flex flex-wrap items-end gap-3">
        {children.length > 0 && <SelectField label="View child" value={targetChild} onChange={(event) => { setChildId(event.target.value); setSelectedId(null); }}>
          {children.map((child) => <option key={child.id} value={child.id}>{child.display_label || child.display_name || child.username}</option>)}
        </SelectField>}
        <CreateGoalForm children={children} initialChildId={targetChild} onCreated={handleCreated} />
      </div>}
      <ErrorAlert message={error || actionError || childrenError} />
      {(error || childrenError) && <Button variant="secondary" onClick={() => { reload(); reloadChildren(); }}>Try again</Button>}
      {selected && <ChallengeGoalDetail goal={selected} {...cardProps} onClose={() => setSelectedId('')} />}
      {!isParent && <DailyChallengeCard challenge={data?.daily_bonus ?? null} />}
      {pinnedGoal && <section className="space-y-3" aria-label="Pinned challenge">
        <SectionHeader title="Pinned to Today" />
        <ChallengeGoalCard goal={pinnedGoal} {...cardProps} />
      </section>}
      <section className="space-y-3" aria-label="Challenges in progress">
        <SectionHeader title="In progress" count={active.length} />
        {active.length ? <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{active.map((goal) => <ChallengeGoalCard key={goal.id} goal={goal} {...cardProps} />)}</div>
          : <EmptyState>{pinnedGoal ? 'Your other matching goals will appear here.' : isParent ? 'Create a challenge for this child to begin.' : 'Your goals will appear here as they become available.'}</EmptyState>}
      </section>
      {upcoming.length > 0 && <section className="space-y-3" aria-label="Upcoming challenges">
        <SectionHeader title="Upcoming" count={upcoming.length} />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{upcoming.map((goal) => <ChallengeGoalCard key={goal.id} goal={goal} {...cardProps} />)}</div>
      </section>}
      <details className="rounded-xl border border-ink-page-shadow p-4">
        <summary className="font-body font-bold text-body text-ink-primary cursor-pointer min-h-11">History · {history.length}</summary>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">{history.length ? history.map((goal) => <ChallengeGoalCard key={goal.id} goal={goal} {...cardProps} />) : <p className="font-body text-body text-ink-secondary">No completed or ended challenges yet.</p>}</div>
      </details>
    </div>
  );
}
