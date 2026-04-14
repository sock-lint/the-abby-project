import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Sparkles } from 'lucide-react';
import { createProject, getCategories, getChildren, getInstructablesPreview } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import ErrorAlert from '../components/ErrorAlert';
import { buttonPrimary, inputClass } from '../constants/styles';
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
        <Card className="space-y-4">
          <ErrorAlert message={error} />

          <div>
            <label className="block text-sm text-ink-whisper mb-1">Title</label>
            <input value={form.title} onChange={set('title')} className={inputClass} required />
          </div>
          <div>
            <label className="block text-sm text-ink-whisper mb-1">Description</label>
            <textarea value={form.description} onChange={set('description')} className={`${inputClass} h-24 resize-none`} />
          </div>
          <div>
            <label className="block text-sm text-ink-whisper mb-1">Instructables URL</label>
            <input
              value={form.instructables_url}
              onChange={set('instructables_url')}
              onBlur={(e) => fetchPreview(e.target.value)}
              className={inputClass}
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
            <div>
              <label className="block text-sm text-ink-whisper mb-1">Category</label>
              <select value={form.category_id} onChange={set('category_id')} className={inputClass}>
                <option value="">None</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm text-ink-whisper mb-1">Difficulty</label>
              <select value={form.difficulty} onChange={set('difficulty')} className={inputClass}>
                {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>)}
              </select>
            </div>
          </div>

          {/* Assignment */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-ink-whisper mb-1">Assign To</label>
              <select value={form.assigned_to_id} onChange={set('assigned_to_id')} className={inputClass}>
                <option value="">{form.payment_kind === 'bounty' ? 'Unassigned (open bounty)' : 'Select a child...'}</option>
                {children.map((c) => (
                  <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-ink-whisper mb-1">Hourly Rate Override ($)</label>
              <input
                value={form.hourly_rate_override}
                onChange={set('hourly_rate_override')}
                className={inputClass}
                type="number"
                step="0.01"
                min="0"
                inputMode="decimal"
                placeholder={form.assigned_to_id
                  ? `Default: $${children.find(c => c.id === parseInt(form.assigned_to_id))?.hourly_rate || '—'}/hr`
                  : 'Select child first'}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-ink-whisper mb-1">Payment Kind</label>
            <select value={form.payment_kind} onChange={set('payment_kind')} className={inputClass}>
              <option value="required">Required (part of allowance)</option>
              <option value="bounty">Bounty (up for grabs, cash reward)</option>
            </select>
            <p className="text-xs text-ink-whisper mt-1">
              {form.payment_kind === 'bounty'
                ? 'Completing this project pays out the bonus as a bounty.'
                : 'Counts toward normal allowance; bonus is a standard project bonus.'}
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-ink-whisper mb-1">
                {form.payment_kind === 'bounty' ? 'Bounty ($)' : 'Bonus ($)'}
              </label>
              <input value={form.bonus_amount} onChange={set('bonus_amount')} className={inputClass} type="number" step="0.01" min="0" inputMode="decimal" />
            </div>
            <div>
              <label className="block text-sm text-ink-whisper mb-1">Materials Budget ($)</label>
              <input value={form.materials_budget} onChange={set('materials_budget')} className={inputClass} type="number" step="0.01" min="0" inputMode="decimal" />
            </div>
            <div>
              <label className="block text-sm text-ink-whisper mb-1">Due Date</label>
              <input value={form.due_date} onChange={set('due_date')} className={inputClass} type="date" />
            </div>
          </div>

          {/* Parent Notes */}
          <div>
            <label className="block text-sm text-ink-whisper mb-1">Parent Notes</label>
            <textarea
              value={form.parent_notes}
              onChange={set('parent_notes')}
              className={`${inputClass} h-20 resize-none`}
              placeholder="Private notes (only visible to parents)"
            />
          </div>

          <button type="submit" className={`w-full py-2.5 ${buttonPrimary}`}>
            Create Project
          </button>
        </Card>
      </form>
    </div>
  );
}
