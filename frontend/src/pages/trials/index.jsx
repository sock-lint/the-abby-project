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
import { SelectField } from '../../components/form';
import DailyChallengeCard from '../../components/dashboard/DailyChallengeCard';
import CreateGoalForm from './CreateGoalForm';
import { ChallengeGoalDetail } from './ChallengeGoalCard';
import ChallengesFolio from './ChallengesFolio';

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
      {searchParams.has('scroll') && <p className="font-body text-caption text-ink-secondary">You can track challenges without spending a scroll. Your saved scroll stays in Inventory.</p>}
      <ErrorAlert message={error || actionError || childrenError} />
      {(error || childrenError) && <Button variant="secondary" onClick={() => { reload(); reloadChildren(); }}>Try again</Button>}
      {selected && <ChallengeGoalDetail goal={selected} {...cardProps} onClose={() => setSelectedId('')} />}
      <ChallengesFolio
        goals={goals} pinnedGoal={pinnedGoal} {...cardProps} isParent={isParent}
        dailyBonus={!isParent && <DailyChallengeCard challenge={data?.daily_bonus ?? null} />}
        toolbar={isParent && <div className="flex flex-wrap items-end gap-3">
          {children.length > 0 && <SelectField label="View child" value={targetChild} onChange={(event) => { setChildId(event.target.value); setSelectedId(null); }}>
            {children.map((child) => <option key={child.id} value={child.id}>{child.display_label || child.display_name || child.username}</option>)}
          </SelectField>}
          <CreateGoalForm children={children} initialChildId={targetChild} onCreated={handleCreated} />
        </div>}
      />
    </div>
  );
}
