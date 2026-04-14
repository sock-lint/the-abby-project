import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import {
  commitIngestJob,
  discardIngestJob,
  getCategories,
  getIngestJob,
  startIngest,
  updateIngestJob,
} from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { normalizeList } from '../utils/api';
import SourceStep from './ingest/SourceStep';
import ReviewStep from './ingest/ReviewStep';

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_MS = 60000;

export default function ProjectIngest() {
  const navigate = useNavigate();
  const { data: categoriesData } = useApi(getCategories);
  const categories = normalizeList(categoriesData);

  const [phase, setPhase] = useState('source'); // source | polling | preview | error
  const [sourceTab, setSourceTab] = useState('url'); // url | pdf
  const [url, setUrl] = useState('');
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  const [jobId, setJobId] = useState(null);
  const [draft, setDraft] = useState(null);
  const [committing, setCommitting] = useState(false);
  const [overrides, setOverrides] = useState({
    category_id: '', difficulty: 2, bonus_amount: '0', materials_budget: '0', due_date: '',
  });

  const pollTimer = useRef(null);

  useEffect(() => () => {
    if (pollTimer.current) clearTimeout(pollTimer.current);
  }, []);

  const beginPolling = (id) => {
    // Capture the start timestamp when polling begins, not when startJob runs,
    // to keep the impure Date.now() call out of the parent's render path.
    const startedAt = Date.now();
    const tick = async () => {
      try {
        const job = await getIngestJob(id);
        if (job.status === 'ready') {
          // Defend against in-flight staging rows that predate the steps/
          // resources fields — rehydrate empty arrays so the editors render.
          const rj = job.result_json || {};
          setDraft({
            ...rj,
            milestones: rj.milestones || [],
            materials: rj.materials || [],
            steps: rj.steps || [],
            resources: rj.resources || [],
          });
          // Seed override defaults from staged draft where possible
          setOverrides((o) => ({ ...o, difficulty: rj.difficulty_hint || o.difficulty }));
          setPhase('preview');
          return;
        }
        if (job.status === 'failed') {
          setError(job.error?.split('\n')[0] || 'Ingestion failed');
          setPhase('error');
          return;
        }
        if (Date.now() - startedAt > POLL_MAX_MS) {
          setError('Ingestion timed out. Try again or use the manual form.');
          setPhase('error');
          return;
        }
        pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
      } catch (err) {
        setError(err.message);
        setPhase('error');
      }
    };
    tick();
  };

  const startJob = async () => {
    setError('');
    try {
      const payload = sourceTab === 'pdf'
        ? { source_type: 'pdf', source_file: file }
        : {
            source_type: url.includes('instructables.com') ? 'instructables' : 'url',
            source_url: url,
          };
      const job = await startIngest(payload);
      setJobId(job.id);
      setPhase('polling');
      beginPolling(job.id);
    } catch (err) {
      setError(err.message);
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
    setCommitting(true);
    setError('');
    try {
      // Persist the edited draft first so the server has the latest copy on
      // commit even if overrides don't carry everything through.
      await updateIngestJob(jobId, { result_json: draft });
      const project = await commitIngestJob(jobId, {
        title: draft.title,
        description: draft.description,
        category_id: overrides.category_id || null,
        difficulty: parseInt(overrides.difficulty, 10) || 2,
        bonus_amount: overrides.bonus_amount || '0',
        materials_budget: overrides.materials_budget || '0',
        due_date: overrides.due_date || null,
        milestones: draft.milestones,
        materials: draft.materials,
        steps: draft.steps,
        resources: draft.resources,
      });
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setError(err.message);
      setCommitting(false);
    }
  };

  const discard = async () => {
    if (jobId) await discardIngestJob(jobId).catch(() => {});
    navigate('/projects');
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <button
        onClick={() => navigate('/projects')}
        className="flex items-center gap-1 text-sm text-forge-text-dim hover:text-forge-text"
      >
        <ArrowLeft size={16} /> Back
      </button>
      <div>
        <h1 className="font-heading text-2xl font-bold">Auto-fill from Source</h1>
        <p className="text-sm text-forge-text-dim mt-1">
          Paste a tutorial link or drop in a PDF. We'll pull the steps, supplies, and category so you can review and confirm.
        </p>
      </div>

      <ErrorAlert message={error} />

      {phase === 'source' && (
        <SourceStep
          sourceTab={sourceTab} setSourceTab={setSourceTab}
          url={url} setUrl={setUrl}
          file={file} setFile={setFile}
          onStart={startJob}
        />
      )}

      {phase === 'polling' && (
        <Card className="flex flex-col items-center py-10 gap-4">
          <Loader />
          <div className="text-sm text-forge-text-dim">Reading the steps…</div>
        </Card>
      )}

      {phase === 'error' && (
        <Card className="space-y-3">
          <p className="text-sm text-forge-text-dim">We couldn't parse that source.</p>
          <div className="flex gap-2">
            <button
              onClick={() => { setPhase('source'); setError(''); }}
              className="px-3 py-2 rounded-lg bg-amber-primary text-black text-sm font-semibold"
            >
              Try Again
            </button>
            <button
              onClick={() => navigate('/projects/new')}
              className="px-3 py-2 rounded-lg border border-forge-border text-sm"
            >
              Manual form
            </button>
          </div>
        </Card>
      )}

      {phase === 'preview' && draft && (
        <ReviewStep
          draft={draft} setDraft={setDraft}
          overrides={overrides} setOverrides={setOverrides}
          categories={categories}
          milestoneHandlers={milestoneHandlers}
          stepHandlers={stepHandlers}
          resourceHandlers={resourceHandlers}
          materialHandlers={materialHandlers}
          committing={committing}
          onCommit={commit}
          onDiscard={discard}
        />
      )}
    </div>
  );
}
