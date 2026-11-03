import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { pinChallenge, retryChallenge, unpinChallenge } from '../../api';
import { useSpace } from '../../hooks/useSpace';
import { getToken } from '../../api/client';
import useChildContext from '../../hooks/useChildContext';
import ChildContext from '../../components/family/ChildContext';
import useChallenges, { CHALLENGES_CHANGED } from '../../hooks/useChallenges';
import useChallengeOpening from '../../hooks/useChallengeOpening';
import useMountedRef from '../../hooks/useMountedRef';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';
import DailyChallengeCard from '../../components/dashboard/DailyChallengeCard';
import CreateGoalForm from './CreateGoalForm';
import FamilyChallengeForm from './FamilyChallengeForm';
import { ChallengeGoalDetail } from './ChallengeGoalCard';
import ChallengesFolio from './ChallengesFolio';
import GoalScheduleControls from './GoalScheduleControls';
import { REWARD_UNAVAILABLE_MESSAGE } from './goalDisplay';
import EggDiscoveryPanel from './EggDiscoveryPanel';

function TrackedChallengeDetail({ user, onConfirmed, ...props }) {
  const { isPersonalSpace } = useSpace();
  useChallengeOpening(props.goal, { user, onConfirmed, personal: isPersonalSpace });
  return <ChallengeGoalDetail {...props} />;
}

export default function Trials() {
  const context = useChildContext();
  if (!context.user?.id || context.loading) return <Loader />;
  if (context.error) return <ErrorAlert message={context.error} onRetry={context.reload} />;
  return <TrialsWorkspace key={`${context.scope}:${context.targetUserId}`} context={context} />;
}

function TrialsWorkspace({ context }) {
  const mounted = useMountedRef();
  const { user, isParent, children = [], targetUserId, selectChild } = context;
  const { isParentAccount, isPersonalSpace } = useSpace();
  const personalParent = isParentAccount && isPersonalSpace;
  const [searchParams, setSearchParams] = useSearchParams();
  const targetChild = isParent ? targetUserId : undefined;
  const { data, goals, pinnedGoal, loading, error, reload, setData } = useChallenges({ userId: targetChild });
  const [selectedId, setSelectedId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const identity = `${context.scope}:${targetUserId}`;
  const identityRef = useRef(identity);
  useEffect(() => { identityRef.current = identity; }, [identity]);
  const selected = goals.find((goal) => goal.id === (selectedId ?? searchParams.get('goal')));
  const timezone = data?.daily_bonus?.timezone || data?.timezone || 'UTC';
  const confirmOpening = ({ id, first_details_opened_at }) => {
    setData((previous) => ({ ...previous, results: previous.results.map((row) => (
      row.id === id && !row.first_details_opened_at ? { ...row, first_details_opened_at } : row
    )) }));
  };

  const handlePin = async (goal) => {
    const requestIdentity = identity;
    const token = getToken();
    const current = () => mounted.current && requestIdentity === identityRef.current && getToken() === token;
    setBusy(true);
    setActionError('');
    try {
      const response = goal.pinned ? await unpinChallenge(goal.id) : await pinChallenge(goal.id);
      if (!current()) return;
      setData((previous) => ({ ...previous, pin: response.pin, results: previous.results.map((row) => ({ ...row, pinned: row.id === response.pin })) }));
      window.dispatchEvent(new Event(CHALLENGES_CHANGED));
    } catch (err) {
      if (current()) setActionError(err.message);
    } finally {
      if (current()) setBusy(false);
    }
  };
  const handleRetry = async (goal) => {
    if (busy || goal.retry?.allowed !== true) return;
    const requestIdentity = identity;
    const token = getToken();
    const current = () => mounted.current && requestIdentity === identityRef.current && getToken() === token;
    setSelectedId(goal.id); setBusy(true); setActionError('');
    try {
      const fresh = await retryChallenge(goal.id, { token });
      if (!current()) return;
      setData((previous) => {
        const pin = fresh.pinned === true ? fresh.id : previous.pin;
        return { ...previous, pin, results: [
          ...previous.results.filter((row) => row.id !== fresh.id).map((row) => ({
            ...row, pinned: row.id === pin,
            ...(row.id === goal.id && { retry: { ...row.retry, allowed: false, latest_attempt_id: fresh.id } }),
          })), fresh,
        ] };
      });
      setSelectedId(fresh.id);
      window.dispatchEvent(new Event(CHALLENGES_CHANGED));
    } catch (failure) {
      if (!current()) return;
      const rewardUnavailable = failure.response?.error === 'reward_unavailable';
      setActionError(rewardUnavailable ? REWARD_UNAVAILABLE_MESSAGE : failure.message || 'Could not start a fresh challenge period.');
      if (rewardUnavailable) setData((previous) => ({ ...previous, results: previous.results.map((row) => (
        row.id === goal.id ? { ...row, retry: { ...row.retry, allowed: false, reason: 'reward_unavailable' } } : row
      )) }));
      if (failure.status === 409) reload();
    } finally { if (current()) setBusy(false); }
  };
  const handleScheduleChanged = (response) => {
    setData((previous) => ({ ...previous, results: previous.results.map((goal) => goal.goal_definition_id === response.goal_definition_id ? { ...goal, schedule: response.schedule } : goal) }));
    window.dispatchEvent(new Event(CHALLENGES_CHANGED));
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
  const cardProps = { timezone, onSelect: (goal) => { setActionError(''); setSelectedId(goal.id); }, onPin: isParent ? undefined : handlePin, onRetry: handleRetry, busy, canAct: !isParent };
  return (
    <div className="space-y-5">
      <EggDiscoveryPanel />
      {searchParams.has('scroll') && <p className="font-body text-caption text-ink-secondary">You can track challenges without spending a scroll. Your saved scroll stays in Inventory.</p>}
      <ErrorAlert message={error || actionError} />
      {error && <Button variant="secondary" onClick={reload}>Try again</Button>}
      {selected && <TrackedChallengeDetail key={selected.id} user={user} onConfirmed={confirmOpening} goal={selected} {...cardProps} actionError={actionError} onClose={() => { setSelectedId(''); setActionError(''); }}
        futureControls={isParentAccount && <GoalScheduleControls goal={selected} onChanged={handleScheduleChanged} onReload={reload} />} />}
      <ChallengesFolio
        goals={goals} lockedCatalog={data?.locked_catalog ?? []} pinnedGoal={pinnedGoal} {...cardProps} isParent={isParent} isPersonalParent={personalParent}
        dailyBonus={!isParent && <DailyChallengeCard challenge={data?.daily_bonus ?? null} />}
        toolbar={isParentAccount && <div className="flex flex-wrap items-end gap-3">
          {isParent && <ChildContext children={children} selectedChildId={targetChild} onSelect={selectChild} />}
          <CreateGoalForm selfUser={personalParent ? user : undefined} children={children} initialChildId={targetChild} onCreated={handleCreated}
            requestOpen={searchParams.get('new') === '1'} onRequestConsumed={() => {
              const next = new URLSearchParams(searchParams);
              next.delete('new');
              setSearchParams(next, { replace: true });
            }} />
          {isParent && <FamilyChallengeForm children={children} onAssigned={() => window.dispatchEvent(new Event(CHALLENGES_CHANGED))} />}
        </div>}
      />
    </div>
  );
}
