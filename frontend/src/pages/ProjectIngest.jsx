import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Link as LinkIcon, FileText, Plus, Trash2 } from 'lucide-react';
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
import DifficultyStars from '../components/DifficultyStars';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { inputClass } from '../constants/styles';
import TabButton from '../components/TabButton';
import { normalizeList } from '../utils/api';

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
      beginPolling(job.id, Date.now());
    } catch (err) {
      setError(err.message);
    }
  };

  const beginPolling = (id, startedAt) => {
    const tick = async () => {
      try {
        const job = await getIngestJob(id);
        if (job.status === 'ready') {
          setDraft(job.result_json);
          // Seed override defaults from staged draft where possible
          setOverrides((o) => ({
            ...o,
            difficulty: job.result_json?.difficulty_hint || o.difficulty,
          }));
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

  const updateMilestone = (i, patch) => {
    setDraft((d) => {
      const milestones = d.milestones.map((m, idx) => (idx === i ? { ...m, ...patch } : m));
      return { ...d, milestones };
    });
  };
  const addMilestone = () => setDraft((d) => ({
    ...d,
    milestones: [...d.milestones, { title: '', description: '', order: d.milestones.length }],
  }));
  const removeMilestone = (i) => setDraft((d) => ({
    ...d,
    milestones: d.milestones.filter((_, idx) => idx !== i).map((m, idx) => ({ ...m, order: idx })),
  }));

  const updateMaterial = (i, patch) => {
    setDraft((d) => {
      const materials = d.materials.map((m, idx) => (idx === i ? { ...m, ...patch } : m));
      return { ...d, materials };
    });
  };
  const addMaterial = () => setDraft((d) => ({
    ...d, materials: [...d.materials, { name: '', description: '', estimated_cost: null }],
  }));
  const removeMaterial = (i) => setDraft((d) => ({
    ...d, materials: d.materials.filter((_, idx) => idx !== i),
  }));

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
      <button onClick={() => navigate('/projects')} className="flex items-center gap-1 text-sm text-forge-text-dim hover:text-forge-text">
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
        <Card className="space-y-4">
          <div className="flex gap-2">
            <TabButton active={sourceTab === 'url'} onClick={() => setSourceTab('url')}>
              <span className="flex items-center gap-2"><LinkIcon size={14} /> URL</span>
            </TabButton>
            <TabButton active={sourceTab === 'pdf'} onClick={() => setSourceTab('pdf')}>
              <span className="flex items-center gap-2"><FileText size={14} /> PDF</span>
            </TabButton>
          </div>

          {sourceTab === 'url' ? (
            <div>
              <label className="block text-sm text-forge-text-dim mb-1">Tutorial URL</label>
              <input
                value={url} onChange={(e) => setUrl(e.target.value)}
                className={inputClass} type="url"
                placeholder="https://www.instructables.com/... or any how-to page"
              />
              <p className="text-xs text-forge-text-dim mt-1">
                Instructables links are parsed in full. Other sites are best-effort.
              </p>
            </div>
          ) : (
            <div>
              <label className="block text-sm text-forge-text-dim mb-1">PDF Tutorial</label>
              <input
                type="file" accept="application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="block w-full text-sm text-forge-text-dim file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-amber-primary file:text-black file:font-semibold"
              />
              {file && <p className="text-xs text-forge-text-dim mt-1">{file.name}</p>}
            </div>
          )}

          <button
            type="button" onClick={startJob}
            disabled={sourceTab === 'url' ? !url : !file}
            className="w-full bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-2.5 rounded-lg transition-colors"
          >
            Parse Source
          </button>
        </Card>
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
            <button onClick={() => { setPhase('source'); setError(''); }} className="px-3 py-2 rounded-lg bg-amber-primary text-black text-sm font-semibold">
              Try Again
            </button>
            <button onClick={() => navigate('/projects/new')} className="px-3 py-2 rounded-lg border border-forge-border text-sm">
              Manual form
            </button>
          </div>
        </Card>
      )}

      {phase === 'preview' && draft && (
        <div className="space-y-4">
          {(draft.warnings?.length > 0 || draft.pipeline_warnings?.length > 0) && (
            <div className="text-xs text-amber-highlight bg-amber-highlight/10 border border-amber-highlight/30 rounded-lg p-3 space-y-1">
              {draft.warnings?.map((w, i) => <div key={`w-${i}`}>⚠ {w}</div>)}
              {draft.pipeline_warnings?.map((w, i) => <div key={`pw-${i}`} className="opacity-70">⚙ {w}</div>)}
            </div>
          )}

          {draft.ai_suggestions && (
            <Card className="border-fuchsia-400/30 bg-fuchsia-400/5 space-y-2">
              <div className="text-xs font-semibold text-fuchsia-300 uppercase tracking-wide">
                ✨ Claude suggestions
              </div>
              {draft.ai_suggestions.summary && (
                <div className="text-sm text-forge-text">{draft.ai_suggestions.summary}</div>
              )}
              <div className="flex flex-wrap gap-2">
                {draft.ai_suggestions.category && (
                  <button
                    type="button"
                    onClick={() => {
                      const match = categories.find(
                        (c) => c.name.toLowerCase() === String(draft.ai_suggestions.category).toLowerCase()
                      );
                      if (match) setOverrides({ ...overrides, category_id: match.id });
                    }}
                    className="text-xs px-2 py-1 rounded-full border border-fuchsia-400/40 text-fuchsia-200 hover:bg-fuchsia-400/10"
                  >
                    Category: {draft.ai_suggestions.category}
                  </button>
                )}
                {draft.ai_suggestions.difficulty && (
                  <button
                    type="button"
                    onClick={() => setOverrides({ ...overrides, difficulty: draft.ai_suggestions.difficulty })}
                    className="text-xs px-2 py-1 rounded-full border border-fuchsia-400/40 text-fuchsia-200 hover:bg-fuchsia-400/10"
                  >
                    Difficulty: <DifficultyStars difficulty={draft.ai_suggestions.difficulty} />
                  </button>
                )}
                {(draft.ai_suggestions.skill_tags || []).map((tag, i) => (
                  <span key={i} className="text-xs px-2 py-1 rounded-full border border-fuchsia-400/40 text-fuchsia-200">
                    {tag}
                  </span>
                ))}
              </div>
              {draft.ai_suggestions.extra_materials?.length > 0 && (
                <div className="text-xs text-forge-text-dim">
                  Suggested extras: {draft.ai_suggestions.extra_materials.map((m) => m.name).join(', ')}
                </div>
              )}
            </Card>
          )}

          <Card className="space-y-4">
            <h2 className="font-heading text-lg font-bold">Review &amp; Edit</h2>

            {draft.cover_photo_url && (
              <img src={draft.cover_photo_url} alt="" className="w-full h-40 object-cover rounded-lg" />
            )}

            <div>
              <label className="block text-sm text-forge-text-dim mb-1">Title</label>
              <input value={draft.title || ''} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className={inputClass} />
            </div>
            <div>
              <label className="block text-sm text-forge-text-dim mb-1">Description</label>
              <textarea value={draft.description || ''} onChange={(e) => setDraft({ ...draft, description: e.target.value })} className={`${inputClass} h-20 resize-none`} />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-forge-text-dim mb-1">Category</label>
                <select
                  value={overrides.category_id}
                  onChange={(e) => setOverrides({ ...overrides, category_id: e.target.value })}
                  className={inputClass}
                >
                  <option value="">
                    {draft.category_hint ? `Suggested: ${draft.category_hint}` : 'None'}
                  </option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-forge-text-dim mb-1">Difficulty</label>
                <select
                  value={overrides.difficulty}
                  onChange={(e) => setOverrides({ ...overrides, difficulty: e.target.value })}
                  className={inputClass}
                >
                  {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>)}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-forge-text-dim mb-1">Bonus ($)</label>
                <input value={overrides.bonus_amount} onChange={(e) => setOverrides({ ...overrides, bonus_amount: e.target.value })} className={inputClass} type="number" step="0.01" min="0" inputMode="decimal" />
              </div>
              <div>
                <label className="block text-sm text-forge-text-dim mb-1">Materials Budget ($)</label>
                <input value={overrides.materials_budget} onChange={(e) => setOverrides({ ...overrides, materials_budget: e.target.value })} className={inputClass} type="number" step="0.01" min="0" inputMode="decimal" />
              </div>
              <div>
                <label className="block text-sm text-forge-text-dim mb-1">Due Date</label>
                <input value={overrides.due_date} onChange={(e) => setOverrides({ ...overrides, due_date: e.target.value })} className={inputClass} type="date" />
              </div>
            </div>
          </Card>

          <Card className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-heading text-lg font-bold">Milestones ({draft.milestones.length})</h2>
              <button onClick={addMilestone} className="text-xs text-amber-primary hover:text-amber-highlight flex items-center gap-1">
                <Plus size={14} /> Add
              </button>
            </div>
            {draft.milestones.map((m, i) => (
              <div key={i} className="bg-forge-bg border border-forge-border rounded-lg p-3 space-y-2">
                <div className="flex gap-2">
                  <input
                    value={m.title} onChange={(e) => updateMilestone(i, { title: e.target.value })}
                    className={inputClass} placeholder={`Step ${i + 1}`}
                  />
                  <button
                    type="button"
                    onClick={() => removeMilestone(i)}
                    aria-label="Remove milestone"
                    className="text-forge-text-dim hover:text-red-400 shrink-0 min-h-10 min-w-10 flex items-center justify-center rounded-lg"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
                <textarea
                  value={m.description || ''}
                  onChange={(e) => updateMilestone(i, { description: e.target.value })}
                  className={`${inputClass} h-16 resize-none text-xs`}
                  placeholder="Description (optional)"
                />
              </div>
            ))}
          </Card>

          <Card className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-heading text-lg font-bold">Materials ({draft.materials.length})</h2>
              <button onClick={addMaterial} className="text-xs text-amber-primary hover:text-amber-highlight flex items-center gap-1">
                <Plus size={14} /> Add
              </button>
            </div>
            {draft.materials.map((m, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={m.name} onChange={(e) => updateMaterial(i, { name: e.target.value })}
                  className={`${inputClass} flex-1`} placeholder="Material name"
                />
                <input
                  value={m.estimated_cost ?? ''}
                  onChange={(e) => updateMaterial(i, { estimated_cost: e.target.value })}
                  className={`${inputClass} w-24`} type="number" step="0.01" min="0" inputMode="decimal" placeholder="$ est."
                />
                <button
                  type="button"
                  onClick={() => removeMaterial(i)}
                  aria-label="Remove material"
                  className="text-forge-text-dim hover:text-red-400 shrink-0 min-h-10 min-w-10 flex items-center justify-center rounded-lg"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            ))}
          </Card>

          <div className="flex gap-2">
            <button
              onClick={commit} disabled={committing}
              className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-2.5 rounded-lg transition-colors"
            >
              {committing ? 'Creating…' : 'Create Project'}
            </button>
            <button onClick={discard} className="px-4 py-2.5 rounded-lg border border-forge-border text-sm text-forge-text-dim">
              Discard
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
