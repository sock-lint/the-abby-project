import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ExternalLink, Sparkles } from 'lucide-react';
import { createProject, getAllCategories, getChildren, getInstructablesPreview } from '../api';
import TaxonomyOptions from '../components/form/TaxonomyOptions';
import { useApi } from '../hooks/useApi';
import { getToken } from '../api/client';
import { usePlanningAccount } from '../components/project-plan/usePlanningAccount';
import { cleanProjectPlan } from '../components/project-plan/projectPlan';
import ProjectAIAssist from './project/ProjectAIAssist';
import Loader from '../components/Loader';
import BackLink from '../components/BackLink';
import ParchmentCard from '../components/journal/ParchmentCard';
import PageShell from '../components/layout/PageShell';
import ErrorAlert from '../components/ErrorAlert';
import Button from '../components/Button';
import { TextField, SelectField, TextAreaField, DueDateChips } from '../components/form';
import { fieldErrors, normalizeList } from '../utils/api';
import { toISODate } from '../utils/dates';
import { usePwaUpdateGuard } from '../pwa/usePwaUpdateGuard';

export default function ProjectNew() {
  const { user, accountKey } = usePlanningAccount();
  if (!user) return <Loader />;
  if (user.role !== 'parent') return <ErrorAlert message="Only parents can create projects." />;
  return <ProjectNewForm key={accountKey} />;
}

function ProjectNewForm() {
  const navigate = useNavigate();
  const { data: categoriesData } = useApi((signal) => getAllCategories({ includeRetired: true, signal }));
  const { data: childrenData } = useApi(getChildren);
  const categories = normalizeList(categoriesData);
  const children = normalizeList(childrenData);

  const [form, setForm] = useState({
    title: '', description: '', instructables_url: '', difficulty: 2,
    category_id: '', bonus_amount: '0', materials_budget: '0', due_date: '',
    payment_kind: 'required', assigned_to_id: '', hourly_rate_override: '',
    parent_notes: '',
  });
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [plan, setPlan] = useState(null);
  const [drafting, setDrafting] = useState(false);
  const [errors, setErrors] = useState({});
  const [token] = useState(getToken);
  const mounted = useRef(false);
  const savingRef = useRef(false);
  const draftingRef = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; previewRequest.current += 1; };
  }, []);
  const isCurrent = () => mounted.current && getToken() === token;
  const initialForm = useRef(form);
  const dirty = Boolean(plan) || Object.keys(initialForm.current).some((key) => form[key] !== initialForm.current[key]);
  usePwaUpdateGuard(dirty || saving || drafting || previewLoading);
  const previewRequest = useRef(0);
  const today = toISODate(new Date());

  const fetchPreview = async (url) => {
    if (!isCurrent()) return;
    const requestId = ++previewRequest.current;
    if (!url || !url.includes('instructables.com')) { setPreview(null); return; }
    setPreviewLoading(true);
    try {
      const data = await getInstructablesPreview(url);
      if (!isCurrent() || requestId !== previewRequest.current) return;
      setPreview(data);
      if (data.title) setForm(prev => prev.title ? prev : { ...prev, title: data.title });
    } catch {
      if (isCurrent() && requestId === previewRequest.current) setPreview(null);
    } finally {
      if (isCurrent() && requestId === previewRequest.current) setPreviewLoading(false);
    }
  };

  const set = (k) => (e) => {
    if (k === 'instructables_url') {
      previewRequest.current += 1;
      setPreview(null);
      setPreviewLoading(false);
    }
    setForm(prev => ({ ...prev, [k]: e.target.value }));
    setErrors(previous => ({ ...previous, [k]: undefined }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (savingRef.current || draftingRef.current || !isCurrent()) return;
    setError('');
    setErrors({});
    savingRef.current = true;
    setSaving(true);
    try {
      const data = {
        ...form,
        difficulty: parseInt(form.difficulty),
        category_id: form.category_id || null,
        due_date: form.due_date || null,
        instructables_url: form.instructables_url || null,
        assigned_to_id: form.assigned_to_id || null,
        hourly_rate_override: form.hourly_rate_override || null,
      };
      if (plan) data.plan_create = cleanProjectPlan(plan);
      const project = await createProject(data);
      if (!isCurrent()) return;
      navigate(`/projects/${project.id}`);
    } catch (err) {
      if (!isCurrent()) return;
      const fields = fieldErrors(err);
      setErrors(fields);
      setError(Object.keys(fields).length ? Object.values(fields).join(' ') : err.message);
    } finally {
      savingRef.current = false;
      if (isCurrent()) setSaving(false);
    }
  };

  return (
    <PageShell width="narrow" rhythm="loose">
      <BackLink to="/quests?tab=ventures">Back to Projects</BackLink>
      <h1 className="font-display text-2xl font-bold">New project</h1>

      <Button
        variant="secondary"
        onClick={() => navigate('/projects/ingest')}
        className="w-full flex items-center gap-3 bg-sheikah-teal/10 hover:bg-sheikah-teal/20 border-sheikah-teal-deep/40 px-4 py-3 text-left"
      >
        <Sparkles size={20} className="text-sheikah-teal-deep shrink-0" />
        <div className="flex-1">
          <div className="text-body font-semibold text-ink-primary">Have a link or PDF?</div>
          <div className="text-caption text-ink-whisper">Auto-fill milestones, materials, and category from the source.</div>
        </div>
        <ExternalLink size={16} className="text-ink-whisper" />
      </Button>

      <form onSubmit={handleSubmit}>
        <ParchmentCard className="space-y-4">
          <ErrorAlert message={error} />

          <TextField label="Title" value={form.title} onChange={set('title')} required maxLength={200} error={errors.title} disabled={saving} />
          <TextAreaField label="Description" value={form.description} onChange={set('description')} rows={3} maxLength={10000} error={errors.description} disabled={saving} />
          <ProjectAIAssist source={{ title: form.title, description: form.description, difficulty: Number(form.difficulty) }}
            plan={plan} onChange={setPlan} disabled={saving} onSourceErrors={setErrors}
            onBusyChange={(value) => { draftingRef.current = value; setDrafting(value); }} />
          <div>
            <TextField
              label="Instructables URL"
              value={form.instructables_url}
              onChange={set('instructables_url')}
              onBlur={(e) => fetchPreview(e.target.value)}
              type="url"
              placeholder="https://www.instructables.com/..."
            />
            {previewLoading && <div className="text-xs text-ink-whisper mt-1">Loading preview...</div>}
            {preview && (
              <div className="mt-2 flex gap-3 bg-ink-page rounded-lg p-3 border border-ink-page-shadow">
                {preview.thumbnail_url && (
                  <img src={preview.thumbnail_url} alt="" className="w-16 h-16 rounded object-cover shrink-0" />
                )}
                <div className="text-xs">
                  <div className="font-medium text-ink-primary">{preview.title}</div>
                  {preview.author && <div className="text-ink-whisper">by {preview.author}</div>}
                  {preview.step_count > 0 && <div className="text-ink-whisper">{preview.step_count} steps</div>}
                </div>
              </div>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SelectField label="Category" value={form.category_id} onChange={set('category_id')}>
              <option value="">None</option>
              <TaxonomyOptions entries={categories} selected={form.category_id} kind="category" />
            </SelectField>
            <SelectField label="Difficulty" value={form.difficulty} onChange={set('difficulty')} error={errors.difficulty} disabled={saving}>
              {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>)}
            </SelectField>
          </div>

          {/* Assignment */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SelectField label="Assign To" value={form.assigned_to_id} onChange={set('assigned_to_id')}>
              <option value="">{form.payment_kind === 'bounty' ? 'Unassigned (available to claim)' : 'Select a child...'}</option>
              {children.map((c) => (
                <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
              ))}
            </SelectField>
            <TextField
              label="Hourly Rate Override ($)"
              value={form.hourly_rate_override}
              onChange={set('hourly_rate_override')}
              type="number"
              step="0.01"
              min="0"
              inputMode="decimal"
              placeholder={form.assigned_to_id
                ? `Default: $${children.find(c => c.id === parseInt(form.assigned_to_id))?.hourly_rate || '—'}/hr`
                : 'Select child first'}
            />
          </div>

          <SelectField
            label="Payment Kind"
            value={form.payment_kind}
            onChange={set('payment_kind')}
            helpText={form.payment_kind === 'bounty'
              ? 'Completing this optional project earns the cash reward.'
              : 'Counts toward normal allowance; bonus is a standard project bonus.'}
          >
            <option value="required">Required (part of allowance)</option>
            <option value="bounty">Optional project (optional, cash reward)</option>
          </SelectField>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <TextField
              label={form.payment_kind === 'bounty' ? 'Cash reward ($)' : 'Bonus ($)'}
              value={form.bonus_amount}
              onChange={set('bonus_amount')}
              type="number"
              step="0.01"
              min="0"
              inputMode="decimal"
            />
            <TextField label="Materials Budget ($)" value={form.materials_budget} onChange={set('materials_budget')} type="number" step="0.01" min="0" inputMode="decimal" />
            <div>
              <TextField label="Due Date" value={form.due_date} onChange={set('due_date')} type="date" min={today} />
              <DueDateChips
                value={form.due_date}
                onSelect={(date) => set('due_date')({ target: { value: date } })}
                className="mt-2"
              />
            </div>
          </div>

          {/* Parent Notes */}
          <TextAreaField
            label="Parent Notes"
            value={form.parent_notes}
            onChange={set('parent_notes')}
            rows={3}
            placeholder="Private notes (only visible to parents)"
          />

          <Button type="submit" className="w-full" loading={saving} disabled={drafting}>
            {saving ? <span>Creating…</span> : 'Create project'}
          </Button>
        </ParchmentCard>
      </form>
    </PageShell>
  );
}
