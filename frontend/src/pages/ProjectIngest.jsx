import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import BackLink from '../components/BackLink';
import {
  commitIngestJob,
  discardIngestJob,
  getCategories,
  getIngestJob,
  startIngest,
  updateIngestJob,
} from '../api';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import { getToken } from '../api/client';
import ParchmentCard from '../components/journal/ParchmentCard';
import PageShell from '../components/layout/PageShell';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import Button from '../components/Button';
import { normalizeList } from '../utils/api';
import SourceStep from './ingest/SourceStep';
import ReviewStep from './ingest/ReviewStep';
import {
  clearIngestDraft, DEFAULT_OVERRIDES, normalizeIngestDraft, readIngestDraft, storeIngestDraft,
} from './ingest/ingestDraft';

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_MS = 60000;

export default function ProjectIngest() {
  const { user } = useRole();
  if (!user) return <Loader />;
  return <IngestForm key={user.id} userId={user.id} />;
}

function IngestForm({ userId }) {
  const navigate = useNavigate();
  const { data: categoriesData } = useApi(getCategories);
  const categories = normalizeList(categoriesData);

  const [restored] = useState(() => readIngestDraft(userId));
  const [snapshot, setSnapshot] = useState(() => restored || {
    jobId: null, draft: null, overrides: DEFAULT_OVERRIDES,
    sourceTab: 'url', url: '', pendingCommit: false,
  });
  const snapshotRef = useRef(snapshot);
  const { jobId, draft, overrides, sourceTab, url, pendingCommit } = snapshot;
  const [phase, setPhase] = useState(restored ? 'polling' : 'source');
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  const [committing, setCommitting] = useState(false);
  const [starting, setStarting] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [storageState, setStorageState] = useState(restored ? 'saved' : 'idle');
  const [syncState, setSyncState] = useState('idle');
  const [sessionToken] = useState(getToken);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const savedDraft = useRef(null);
  const saveQueue = useRef(Promise.resolve());

  const isCurrentSession = useCallback(
    () => mounted.current && getToken() === sessionToken,
    [sessionToken],
  );

  const changeSnapshot = useCallback((patch) => {
    if (!isCurrentSession()) return;
    const next = { ...snapshotRef.current, ...patch };
    snapshotRef.current = next;
    if (next.jobId) setStorageState(storeIngestDraft(userId, next) ? 'saved' : 'unavailable');
    setSnapshot(next);
    return next;
  }, [isCurrentSession, userId]);

  const setDraft = (next) => {
    setSyncState('idle');
    changeSnapshot({ draft: typeof next === 'function' ? next(snapshotRef.current.draft) : next });
  };
  const setOverrides = (next) => changeSnapshot({
    overrides: typeof next === 'function' ? next(snapshotRef.current.overrides) : next,
  });
  const setSourceTab = (next) => changeSnapshot({ sourceTab: next });
  const setUrl = (next) => changeSnapshot({ url: next });

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const openProject = useCallback((project) => {
    if (!isCurrentSession()) return;
    clearIngestDraft(userId, snapshotRef.current.jobId);
    navigate(`/quests/ventures/${typeof project === 'object' ? project.id : project}`);
  }, [isCurrentSession, navigate, userId]);

  useEffect(() => {
    if (phase !== 'polling' || !jobId) return;
    const startedAt = Date.now();
    let cancelled = false;
    let timer;
    const tick = async () => {
      try {
        const job = await getIngestJob(jobId);
        if (cancelled || !isCurrentSession()) return;
        if (job.status === 'committed') {
          if (job.project) openProject(job.project);
          else {
            setError('The project created from this import has been removed. You can start a fresh import.');
            setPhase('missing');
          }
          return;
        }
        if (job.status === 'ready') {
          const serverDraft = normalizeIngestDraft(job.result_json || {});
          savedDraft.current = JSON.stringify(serverDraft);
          const current = snapshotRef.current;
          changeSnapshot({
            draft: current.draft || serverDraft,
            overrides: current.draft ? current.overrides : {
              ...current.overrides, difficulty: serverDraft.difficulty_hint || current.overrides.difficulty,
            },
          });
          setError('');
          setPhase(current.pendingCommit ? 'uncertain' : 'preview');
          return;
        }
        if (job.status === 'discarded') {
          setError('This import was discarded. You can start a fresh import.');
          setPhase('missing');
          return;
        }
        if (job.status === 'failed') {
          changeSnapshot({ pendingCommit: false });
          setError(job.error?.split('\n')[0] || 'Ingestion failed');
          setPhase('failed');
          return;
        }
        if (Date.now() - startedAt > POLL_MAX_MS) {
          setError('This import is taking longer than expected. Check the existing import to continue.');
          setPhase('paused');
          return;
        }
        timer = setTimeout(tick, POLL_INTERVAL_MS);
      } catch (err) {
        if (cancelled || !isCurrentSession()) return;
        setError(err.message);
        setPhase(err.status === 404 ? 'missing' : 'paused');
      }
    };
    tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [phase, jobId, changeSnapshot, isCurrentSession, openProject]);

  const saveStaging = useCallback((current) => {
    // Serialize PATCHes so a slower, older autosave cannot undo newer edits.
    const request = saveQueue.current.catch(() => {}).then(async () => {
      if (!isCurrentSession()) return;
      await updateIngestJob(current.jobId, { result_json: current.draft });
      if (isCurrentSession()) savedDraft.current = JSON.stringify(current.draft);
    });
    saveQueue.current = request;
    return request;
  }, [isCurrentSession]);

  useEffect(() => {
    if (phase !== 'preview' || !draft || committing || discarding || pendingCommit
      || JSON.stringify(draft) === savedDraft.current) return;
    const timer = setTimeout(async () => {
      setSyncState('saving');
      try {
        await saveStaging(snapshotRef.current);
        if (isCurrentSession()) setSyncState(
          JSON.stringify(snapshotRef.current.draft) === savedDraft.current ? 'saved' : 'idle',
        );
      } catch {
        if (isCurrentSession()) setSyncState('failed');
      }
    }, 700);
    return () => clearTimeout(timer);
  }, [phase, draft, committing, discarding, pendingCommit, saveStaging, isCurrentSession]);

  const startJob = async () => {
    if (inFlight.current || jobId) return;
    inFlight.current = true;
    setError('');
    setStarting(true);
    try {
      const payload = sourceTab === 'pdf'
        ? { source_type: 'pdf', source_file: file }
        : {
            source_type: url.includes('instructables.com') ? 'instructables' : 'url',
            source_url: url,
          };
      const job = await startIngest(payload);
      if (!isCurrentSession()) {
        // Leaving the page during upload must not orphan the job whose ID
        // arrives later. Keep it only if this session still owns the response
        // and no newer import has already claimed this user's draft slot.
        if (getToken() === sessionToken && !readIngestDraft(userId)) {
          storeIngestDraft(userId, { ...snapshotRef.current, jobId: job.id });
        }
        return;
      }
      changeSnapshot({ jobId: job.id });
      setPhase('polling');
    } catch (err) {
      if (isCurrentSession()) setError(err.message);
    } finally {
      inFlight.current = false;
      if (isCurrentSession()) setStarting(false);
    }
  };

  // ── Draft mutation handlers ──────────────────────────────────────────────
  // Cross-cutting helpers (removeMilestone shifts step.milestone_index;
  // removeStep shifts resource.step_index) live here so the per-section
  // editors stay presentational.

  const milestoneHandlers = {
    add: () => setDraft((d) => ({
      ...d,
      milestones: [...d.milestones, { title: '', description: '', order: d.milestones.length }],
    })),
    update: (i, patch) => setDraft((d) => ({
      ...d,
      milestones: d.milestones.map((m, idx) => (idx === i ? { ...m, ...patch } : m)),
    })),
    remove: (i) => setDraft((d) => ({
      ...d,
      milestones: d.milestones.filter((_, idx) => idx !== i).map((m, idx) => ({ ...m, order: idx })),
      // Shift step.milestone_index so steps stay pointing at the right
      // milestone after the removal. Steps attached to the removed milestone
      // become loose (null).
      steps: (d.steps || []).map((s) => {
        if (s.milestone_index == null) return s;
        if (s.milestone_index === i) return { ...s, milestone_index: null };
        if (s.milestone_index > i) return { ...s, milestone_index: s.milestone_index - 1 };
        return s;
      }),
    })),
  };

  const stepHandlers = {
    add: () => setDraft((d) => ({
      ...d,
      steps: [
        ...d.steps,
        { title: '', description: '', order: d.steps.length, milestone_index: null },
      ],
    })),
    update: (i, patch) => setDraft((d) => ({
      ...d,
      steps: d.steps.map((s, idx) => (idx === i ? { ...s, ...patch } : s)),
    })),
    remove: (i) => setDraft((d) => ({
      ...d,
      // Drop the step, reindex ordering, and reshuffle resources attached to
      // later steps so step_index stays valid post-removal.
      steps: d.steps.filter((_, idx) => idx !== i).map((s, idx) => ({ ...s, order: idx })),
      resources: (d.resources || []).flatMap((r) => {
        if (r.step_index == null) return [r];
        if (r.step_index === i) return [{ ...r, step_index: null }];
        if (r.step_index > i) return [{ ...r, step_index: r.step_index - 1 }];
        return [r];
      }),
    })),
  };

  const resourceHandlers = {
    add: () => setDraft((d) => ({
      ...d,
      resources: [
        ...(d.resources || []),
        { url: '', title: '', resource_type: 'link', order: (d.resources || []).length, step_index: null },
      ],
    })),
    update: (i, patch) => setDraft((d) => ({
      ...d,
      resources: d.resources.map((r, idx) => (idx === i ? { ...r, ...patch } : r)),
    })),
    remove: (i) => setDraft((d) => ({
      ...d,
      resources: (d.resources || []).filter((_, idx) => idx !== i),
    })),
  };

  const materialHandlers = {
    add: () => setDraft((d) => ({
      ...d,
      materials: [...d.materials, { name: '', description: '', estimated_cost: null }],
    })),
    update: (i, patch) => setDraft((d) => ({
      ...d,
      materials: d.materials.map((m, idx) => (idx === i ? { ...m, ...patch } : m)),
    })),
    remove: (i) => setDraft((d) => ({
      ...d,
      materials: d.materials.filter((_, idx) => idx !== i),
    })),
  };

  const commit = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setCommitting(true);
    setError('');
    try {
      const current = snapshotRef.current;
      const job = await getIngestJob(current.jobId);
      if (!isCurrentSession()) return;
      if (job.status === 'committed') {
        if (job.project) openProject(job.project);
        else {
          setError('The project created from this import has been removed. You can start a fresh import.');
          setPhase('missing');
        }
        return;
      }
      if (job.status !== 'ready') {
        setError('The import is not ready yet. Check its progress to continue.');
        setPhase('paused');
        return;
      }
      // Finish queued autosaves before recording the immutable creation request.
      // On a retry the original draft/overrides stay frozen; the same job's
      // idempotent commit endpoint returns its project if it already succeeded.
      if (!current.pendingCommit) await saveStaging(current);
      if (!isCurrentSession()) return;
      changeSnapshot({ pendingCommit: true });
      const project = await commitIngestJob(current.jobId, {
        title: current.draft.title,
        description: current.draft.description,
        category_id: current.overrides.category_id || null,
        difficulty: parseInt(current.overrides.difficulty, 10) || 2,
        bonus_amount: current.overrides.bonus_amount || '0',
        materials_budget: current.overrides.materials_budget || '0',
        due_date: current.overrides.due_date || null,
        milestones: current.draft.milestones,
        materials: current.draft.materials,
        steps: current.draft.steps,
        resources: current.draft.resources,
      });
      openProject(project);
    } catch (err) {
      if (!isCurrentSession()) return;
      if (err.status === 404) {
        setError(err.message);
        setPhase('missing');
      } else if (err.status === 409) {
        // A staging save can conflict with another tab's successful commit.
        // Reload the job before deciding whether to open or forget it.
        setError(err.message);
        setPhase('polling');
      } else if (snapshotRef.current.pendingCommit && !(err.status >= 400 && err.status < 500)) {
        setError('We could not confirm creation. Check creation to safely finish this same import.');
        setPhase('uncertain');
      } else {
        changeSnapshot({ pendingCommit: false });
        setError(err.message);
        setPhase('preview');
      }
    } finally {
      inFlight.current = false;
      if (isCurrentSession()) setCommitting(false);
    }
  };

  const discard = async (restart = false) => {
    if (inFlight.current || pendingCommit) return;
    inFlight.current = true;
    setDiscarding(true);
    setError('');
    try {
      await saveQueue.current.catch(() => {});
      await discardIngestJob(jobId);
      if (!isCurrentSession()) return;
      clearIngestDraft(userId, jobId);
      if (restart) {
        changeSnapshot({ jobId: null, draft: null, overrides: DEFAULT_OVERRIDES, pendingCommit: false });
        setStorageState('idle');
        setSyncState('idle');
        setPhase('source');
      } else {
        navigate('/quests?tab=ventures');
      }
    } catch (err) {
      if (isCurrentSession()) {
        setError(err.message || 'Could not discard the import. Try again.');
        if (err.status === 404) setPhase('missing');
        else if (err.status === 409) setPhase('polling');
      }
    } finally {
      inFlight.current = false;
      if (isCurrentSession()) setDiscarding(false);
    }
  };

  const resume = () => { setError(''); setPhase('polling'); };
  const forget = () => {
    clearIngestDraft(userId, jobId);
    changeSnapshot({ jobId: null, draft: null, overrides: DEFAULT_OVERRIDES, pendingCommit: false });
    setStorageState('idle');
    setSyncState('idle');
    setError('');
    setPhase('source');
  };

  return (
    <PageShell width="narrow" rhythm="loose">
      <BackLink to="/quests?tab=ventures">Back to Projects</BackLink>
      <div>
        <h1 className="font-display text-2xl font-bold">Auto-fill from Source</h1>
        <p className="text-body text-ink-whisper mt-1">
          Paste a tutorial link or drop in a PDF. We'll pull the steps, supplies, and category so you can review and confirm.
        </p>
      </div>

      <ErrorAlert message={error} />

      {jobId && (
        <div role="status" aria-live="polite" className="space-y-1 text-caption text-ink-whisper">
          {restored?.jobId === jobId && <p>Your unfinished import was restored.</p>}
          <p>{pendingCommit ? 'Creation is not confirmed yet. Your original plan is kept for a safe retry.'
            : storageState === 'unavailable' ? 'This browser cannot keep a draft. Keep this window open until you create the project.'
              : 'Your import and edits are kept on this device. The project has not been created yet.'}</p>
          {syncState === 'saving' && <p>Saving the edited plan…</p>}
          {syncState === 'saved' && <p>The edited plan is saved with this import.</p>}
          {syncState === 'failed' && <p>{storageState === 'saved'
            ? 'The plan could not sync. Your device draft is kept; creating the project will try again.'
            : 'The plan could not sync. Keep this window open and try creating the project again.'}</p>}
        </div>
      )}

      {phase === 'source' && (
        <SourceStep
          sourceTab={sourceTab} setSourceTab={setSourceTab}
          url={url} setUrl={setUrl}
          file={file} setFile={setFile}
          onStart={startJob}
          starting={starting}
        />
      )}

      {phase === 'polling' && (
        <ParchmentCard className="flex flex-col items-center py-10 gap-4">
          <Loader />
          <div className="text-body text-ink-whisper">Reading the steps…</div>
        </ParchmentCard>
      )}

      {['paused', 'failed', 'uncertain', 'missing'].includes(phase) && (
        <ParchmentCard className="space-y-3">
          <p className="text-body text-ink-whisper">
            {phase === 'missing' ? 'This saved import is no longer available.'
              : phase === 'failed' ? 'This import could not be completed.'
              : phase === 'uncertain' ? 'Check whether your project was created before continuing.'
                : 'Your existing import is kept. Continue when your connection returns.'}
          </p>
          <div className="flex flex-wrap gap-2">
            {phase === 'missing' ? (
              <Button size="sm" onClick={forget}>Forget this import & start again</Button>
            ) : phase === 'uncertain' ? (
              <Button size="sm" onClick={commit} loading={committing}>Check creation</Button>
            ) : phase === 'paused' ? (
              <Button size="sm" onClick={resume}>Check import</Button>
            ) : (
              <Button size="sm" onClick={() => discard(true)} loading={discarding}>Discard & start again</Button>
            )}
            {!pendingCommit && phase === 'paused' && (
              <Button size="sm" variant="secondary" onClick={() => discard()} disabled={discarding}>
                Discard import
              </Button>
            )}
          </div>
        </ParchmentCard>
      )}

      {phase === 'preview' && draft && (
        <fieldset disabled={committing || discarding} className="min-w-0">
          <ReviewStep
            draft={draft} setDraft={setDraft}
            overrides={overrides} setOverrides={setOverrides}
            categories={categories}
            milestoneHandlers={milestoneHandlers}
            stepHandlers={stepHandlers}
            resourceHandlers={resourceHandlers}
            materialHandlers={materialHandlers}
            committing={committing || discarding}
            onCommit={commit}
            onDiscard={() => discard()}
          />
        </fieldset>
      )}
    </PageShell>
  );
}
