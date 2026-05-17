import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import IncipitBand from '../../components/atlas/IncipitBand';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import {
  getActiveQuest, getAvailableQuests, getQuestHistory, getFamilyQuests,
  getChildren, startQuest, getSkills, getBadges,
} from '../../api';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import { normalizeList } from '../../utils/api';
import ActiveQuestFolio from './ActiveQuestFolio';
import FamilyTrialsFolio from './FamilyTrialsFolio';
import IssueChallengeForm from './IssueChallengeForm';
import QuestCodex from './QuestCodex';
import { overallProgress } from './trials.constants';

/**
 * Trials — the boss/collection quest surface, rebuilt to speak the
 * illuminated-manuscript vocabulary the Bestiary established:
 *
 *   - IncipitBand hero with the gilt drop-cap
 *   - ActiveQuestFolio (verso/recto) for the in-progress quest
 *   - FamilyTrialsFolio with ChapterRubric for the parent roll-up
 *   - QuestCodex — vessel kind shelf + codex chapter shelf + folio body
 *   - IssueChallengeForm (parent-only) for custom campaigns
 *
 * The page lives at /quests?tab=trials (added as the 6th tab of the
 * Quests hub) and is reachable via /trials (which redirects, preserving
 * any query string such as ?scroll=<itemId>).
 */
export default function Trials() {
  const [searchParams] = useSearchParams();
  const scrollItemId = searchParams.get('scroll') || undefined;
  const { isParent } = useRole();

  const { data: activeQuest, loading: loadingActive, reload: reloadActive } = useApi(getActiveQuest);
  const { data: availableData, loading: loadingAvailable } = useApi(getAvailableQuests);
  const { data: historyData, loading: loadingHistory } = useApi(getQuestHistory);
  const { data: badgesData, loading: loadingBadges } = useApi(getBadges);

  const fetchFamily = useCallback(
    () => (isParent ? getFamilyQuests() : Promise.resolve({ results: [] })),
    [isParent],
  );
  const { data: familyData, loading: loadingFamily, reload: reloadFamily } = useApi(fetchFamily, [isParent]);

  const fetchKids = useCallback(
    () => (isParent ? getChildren() : Promise.resolve({ results: [] })),
    [isParent],
  );
  const { data: childrenData } = useApi(fetchKids, [isParent]);

  const fetchSkills = useCallback(
    () => (isParent ? getSkills() : Promise.resolve({ results: [] })),
    [isParent],
  );
  const { data: skillsData } = useApi(fetchSkills, [isParent]);

  const [error, setError] = useState('');
  const [starting, setStarting] = useState(null);

  const available = useMemo(() => normalizeList(availableData), [availableData]);
  const history = useMemo(() => normalizeList(historyData), [historyData]);
  const children = useMemo(() => normalizeList(childrenData), [childrenData]);
  const skills = useMemo(() => normalizeList(skillsData), [skillsData]);

  // Earned-badge ids drive the locked classifier in trials.constants.
  // getBadges() returns the catalog with an `earned` flag on each row —
  // we keep just the ids the user has earned in a Set for O(1) lookup.
  const earnedBadgeIds = useMemo(() => {
    const list = normalizeList(badgesData);
    return new Set(list.filter((b) => b.earned).map((b) => b.id));
  }, [badgesData]);

  const familyRows = useMemo(
    () => (familyData?.results || []).filter((row) => row.quest),
    [familyData],
  );

  const progress = useMemo(
    () => overallProgress({ history, available, activeQuest }),
    [history, available, activeQuest],
  );

  const loading = loadingActive || loadingAvailable || loadingHistory || loadingFamily || loadingBadges;
  if (loading) return <Loader />;

  const handleBegin = async (def) => {
    setStarting(def.id);
    setError('');
    try {
      await startQuest(def.id, scrollItemId);
      reloadActive();
    } catch (e) {
      setError(e.message);
    } finally {
      setStarting(null);
    }
  };

  return (
    <div className="space-y-6">
      <IncipitBand
        letter="T"
        title="Trials"
        kicker="· boss campaigns & collection hunts ·"
        meta={(
          <>
            <span className="tabular-nums">{progress.triumphs} of {progress.total}</span>
            <span>triumphed</span>
          </>
        )}
        progressPct={progress.progressPct}
      />

      <p className="font-script text-sm text-ink-whisper -mt-2 max-w-xl">
        boss trials take damage from your work and study · collection trials count items earned · only one active at a time
      </p>

      <ErrorAlert message={error} />

      {isParent && (
        <IssueChallengeForm
          children={children}
          skills={skills}
          onIssued={() => { reloadFamily(); reloadActive(); }}
          onError={setError}
        />
      )}

      {activeQuest && <ActiveQuestFolio quest={activeQuest} />}

      {isParent && familyRows.length > 0 && (
        <FamilyTrialsFolio rows={familyRows} />
      )}

      <QuestCodex
        available={available}
        activeQuest={activeQuest}
        history={history}
        earnedBadgeIds={earnedBadgeIds}
        starting={starting}
        onBegin={handleBegin}
      />
    </div>
  );
}
