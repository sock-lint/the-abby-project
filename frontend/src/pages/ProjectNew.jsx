import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Sparkles } from 'lucide-react';
import { createProject, getCategories, getChildren, getInstructablesPreview } from '../api';
import { useApi } from '../hooks/useApi';
import ParchmentCard from '../components/journal/ParchmentCard';
import ErrorAlert from '../components/ErrorAlert';
import Button from '../components/Button';
import { TextField, SelectField, TextAreaField } from '../components/form';
import { normalizeList } from '../utils/api';

export default function ProjectNew() {
  const navigate = useNavigate();
  const { data: categoriesData } = useApi(getCategories);
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

  const fetchPreview = async (url) => {
    if (!url || !url.includes('instructables.com')) { setPreview(null); return; }
    setPreviewLoading(true);
    try {
      const data = await getInstructablesPreview(url);
      setPreview(data);
      if (data.title && !form.title) setForm(prev => ({ ...prev, title: data.title }));
    } catch { setPreview(null); }
    setPreviewLoading(false);
  };

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
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
      const project = await createProject(data);
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <button onClick={() => navigate('/projects')} className="flex items-center gap-1 text-sm text-ink-whisper hover:text-ink-primary">
        <ArrowLeft size={16} /> Back
      </button>
      <h1 className="font-display text-2xl font-bold">New Project</h1>

      <button
        type="button"
        onClick={() => navigate('/projects/ingest')}
        className="w-full flex items-center gap-3 bg-sheikah-teal/10 hover:bg-sheikah-teal/20 border border-sheikah-teal-deep/40 rounded-lg px-4 py-3 text-left transition-colors"
      >
        <Sparkles size={20} className="text-sheikah-teal-deep shrink-0" />
        <div className="flex-1">
          <div className="text-sm font-semibold text-ink-primary">Have a link or PDF?</div>
          <div className="text-xs text-ink-whisper">Auto-fill milestones, materials, and category from the source.</div>
        </div>
        <ExternalLink size={16} className="text-ink-whisper" />
      </button>

      <form onSubmit={handleSubmit}>
        <ParchmentCard className="space-y-4">
          <ErrorAlert message={error} />

          <TextField label="Title" value={form.title} onChange={set('title')} required />
          <TextAreaField label="Description" value={form.description} onChange={set('description')} rows={3} />
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
              {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
            </SelectField>
            <SelectField label="Difficulty" value={form.difficulty} onChange={set('difficulty')}>
              {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>)}
            </SelectField>
          </div>

          {/* Assignment */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SelectField label="Assign To" value={form.assigned_to_id} onChange={set('assigned_to_id')}>
              <option value="">{form.payment_kind === 'bounty' ? 'Unassigned (open bounty)' : 'Select a child...'}</option>
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
              ? 'Completing this project pays out the bonus as a bounty.'
              : 'Counts toward normal allowance; bonus is a standard project bonus.'}
          >
            <option value="required">Required (part of allowance)</option>
            <option value="bounty">Bounty (up for grabs, cash reward)</option>
          </SelectField>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <TextField
              label={form.payment_kind === 'bounty' ? 'Bounty ($)' : 'Bonus ($)'}
              value={form.bonus_amount}
              onChange={set('bonus_amount')}
              type="number"
              step="0.01"
              min="0"
              inputMode="decimal"
            />
            <TextField label="Materials Budget ($)" value={form.materials_budget} onChange={set('materials_budget')} type="number" step="0.01" min="0" inputMode="decimal" />
            <TextField label="Due Date" value={form.due_date} onChange={set('due_date')} type="date" />
          </div>

          {/* Parent Notes */}
          <TextAreaField
            label="Parent Notes"
            value={form.parent_notes}
            onChange={set('parent_notes')}
            rows={3}
            placeholder="Private notes (only visible to parents)"
          />

          <Button type="submit" className="w-full">
            Create Project
          </Button>
        </ParchmentCard>
      </form>
    </div>
  );
}
