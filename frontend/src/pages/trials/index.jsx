import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { pinChallenge, unpinChallenge } from '../../api';
import { getToken } from '../../api/client';
import useChildContext from '../../hooks/useChildContext';
import ChildContext from '../../components/family/ChildContext';
import useChallenges, { CHALLENGES_CHANGED } from '../../hooks/useChallenges';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';
import DailyChallengeCard from '../../components/dashboard/DailyChallengeCard';
import CreateGoalForm from './CreateGoalForm';
import { ChallengeGoalDetail } from './ChallengeGoalCard';
import ChallengesFolio from './ChallengesFolio';

export default function Trials() {
  const context = useChildContext();
  if (!context.user?.id || context.loading) return <Loader />;
  if (context.error) return <ErrorAlert message={context.error} onRetry={context.reload} />;
  return <TrialsWorkspace key={`${context.scope}:${context.targetUserId}`} context={context} />;
}

function TrialsWorkspace({ context }) {
  const { user, isParent, children = [], targetUserId, selectChild } = context;
  const [searchParams, setSearchParams] = useSearchParams();
  const targetChild = isParent ? targetUserId : undefined;
  const { data, goals, pinnedGoal, loading, error, reload, setData } = useChallenges({ userId: targetChild });
  const [selectedId, setSelectedId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const identity = `${user?.id}:${getToken()}`;
  const identityRef = useRef(identity);
  useEffect(() => { identityRef.current = identity; }, [identity]);
  const selected = goals.find((goal) => goal.id === (selectedId ?? searchParams.get('goal')));
  const timezone = data?.daily_bonus?.timezone || data?.timezone || 'UTC';

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
    if (String(assigneeId) !== String(targetChild) && children.some((child) => String(child.id) === String(assigneeId))) {
      const next = new URLSearchParams(searchParams);
      next.set('child', String(assigneeId));
      next.set('goal', created.id);
      setSearchParams(next, { replace: true });
    } else reload();
  };
  if (loading || !user) return <Loader />;
  const cardProps = { timezone, onSelect: (goal) => setSelectedId(goal.id), onPin: isParent ? undefined : handlePin, busy, canAct: !isParent };
  return (
    <div className="space-y-5">
      {searchParams.has('scroll') && <p className="font-body text-caption text-ink-secondary">You can track challenges without spending a scroll. Your saved scroll stays in Inventory.</p>}
      <ErrorAlert message={error || actionError} />
      {error && <Button variant="secondary" onClick={reload}>Try again</Button>}
      {selected && <ChallengeGoalDetail goal={selected} {...cardProps} onClose={() => setSelectedId('')} />}
      <ChallengesFolio
        goals={goals} pinnedGoal={pinnedGoal} {...cardProps} isParent={isParent}
        dailyBonus={!isParent && <DailyChallengeCard challenge={data?.daily_bonus ?? null} />}
        toolbar={isParent && <div className="flex flex-wrap items-end gap-3">
          <ChildContext children={children} selectedChildId={targetChild} onSelect={selectChild} />
          <CreateGoalForm children={children} initialChildId={targetChild} onCreated={handleCreated}
            requestOpen={searchParams.get('new') === '1'} onRequestConsumed={() => {
              const next = new URLSearchParams(searchParams);
              next.delete('new');
              setSearchParams(next, { replace: true });
            }} />
        </div>}
      />
    </div>
  );
}
