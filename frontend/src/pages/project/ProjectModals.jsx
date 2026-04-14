import { useState } from 'react';
import {
  updateProject,
  createMilestone, createMaterial, createStep, createResource,
  getCategories, getChildren,
} from '../../api';
import { useApi } from '../../hooks/useApi';
import BottomSheet from '../../components/BottomSheet';
import ErrorAlert from '../../components/ErrorAlert';
import { inputClass } from '../../constants/styles';
import { normalizeList } from '../../utils/api';

/* ── Edit Project Modal ─────────────────────────────────────────── */

export function EditProjectModal({ project, onClose, onSaved }) {
  const { data: categoriesData } = useApi(getCategories);
  const { data: childrenData } = useApi(getChildren);
  const categories = normalizeList(categoriesData);
  const children = normalizeList(childrenData);

  const [form, setForm] = useState({
    title: project.title || '',
    description: project.description || '',
    difficulty: project.difficulty || 2,
    category_id: project.category?.id || '',
    assigned_to_id: project.assigned_to?.id || '',
    bonus_amount: project.bonus_amount || '0',
    payment_kind: project.payment_kind || 'required',
    hourly_rate_override: project.hourly_rate_override || '',
    materials_budget: project.materials_budget || '0',
    due_date: project.due_date || '',
    parent_notes: project.parent_notes || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await updateProject(project.id, {
        ...form,
        difficulty: parseInt(form.difficulty),
        category_id: form.category_id || null,
        assigned_to_id: form.assigned_to_id || null,
        hourly_rate_override: form.hourly_rate_override || null,
        due_date: form.due_date || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Edit Project" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Title</label>
          <input value={form.title} onChange={set('title')} className={inputClass} required />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Description</label>
          <textarea value={form.description} onChange={set('description')} className={`${inputClass} h-20 resize-none`} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Category</label>
            <select value={form.category_id} onChange={set('category_id')} className={inputClass}>
              <option value="">None</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Difficulty</label>
            <select value={form.difficulty} onChange={set('difficulty')} className={inputClass}>
              {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>)}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Assign To</label>
            <select value={form.assigned_to_id} onChange={set('assigned_to_id')} className={inputClass}>
              <option value="">Unassigned</option>
              {children.map((c) => (
                <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Payment Kind</label>
            <select value={form.payment_kind} onChange={set('payment_kind')} className={inputClass}>
              <option value="required">Required</option>
              <option value="bounty">Bounty</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">
              {form.payment_kind === 'bounty' ? 'Bounty ($)' : 'Bonus ($)'}
            </label>
            <input value={form.bonus_amount} onChange={set('bonus_amount')} className={inputClass} type="number" step="0.01" min="0" />
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Budget ($)</label>
            <input value={form.materials_budget} onChange={set('materials_budget')} className={inputClass} type="number" step="0.01" min="0" />
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Rate Override ($)</label>
            <input value={form.hourly_rate_override} onChange={set('hourly_rate_override')} className={inputClass} type="number" step="0.01" min="0" placeholder="Default" />
          </div>
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Due Date</label>
          <input value={form.due_date} onChange={set('due_date')} className={inputClass} type="date" />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Parent Notes</label>
          <textarea value={form.parent_notes} onChange={set('parent_notes')} className={`${inputClass} h-16 resize-none`} placeholder="Private notes" />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Add Milestone Modal ────────────────────────────────────────── */

export function AddMilestoneModal({ projectId, onClose, onSaved }) {
  const [form, setForm] = useState({ title: '', description: '', bonus_amount: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await createMilestone(projectId, {
        project: projectId,
        title: form.title,
        description: form.description,
        bonus_amount: form.bonus_amount || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Milestone" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Title</label>
          <input value={form.title} onChange={set('title')} className={inputClass} required autoFocus />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Description</label>
          <textarea value={form.description} onChange={set('description')} className={`${inputClass} h-16 resize-none`} />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Bonus ($)</label>
          <input value={form.bonus_amount} onChange={set('bonus_amount')} className={inputClass} type="number" step="0.01" min="0" placeholder="Optional" />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.title.trim()} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Adding...' : 'Add Milestone'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Add Material Modal ─────────────────────────────────────────── */

export function AddMaterialModal({ projectId, onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', description: '', estimated_cost: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await createMaterial(projectId, {
        project: projectId,
        name: form.name,
        description: form.description,
        estimated_cost: form.estimated_cost || '0',
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Material" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Name</label>
          <input value={form.name} onChange={set('name')} className={inputClass} required autoFocus />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Description</label>
          <textarea value={form.description} onChange={set('description')} className={`${inputClass} h-16 resize-none`} />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Estimated Cost ($)</label>
          <input value={form.estimated_cost} onChange={set('estimated_cost')} className={inputClass} type="number" step="0.01" min="0" />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.name.trim()} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Adding...' : 'Add Material'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Add Step Modal ─────────────────────────────────────────────── */

export function AddStepModal({ projectId, milestones = [], initialMilestoneId = null, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: '',
    description: '',
    milestone: initialMilestoneId == null ? '' : String(initialMilestoneId),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await createStep(projectId, {
        project: projectId,
        title: form.title,
        description: form.description,
        milestone: form.milestone === '' ? null : Number(form.milestone),
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Step" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <p className="text-xs text-forge-text-dim">
          Steps are walkthrough instructions — no coins, XP, or ledger impact.
        </p>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Title</label>
          <input value={form.title} onChange={set('title')} className={inputClass} required autoFocus />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Description</label>
          <textarea
            value={form.description}
            onChange={set('description')}
            className={`${inputClass} h-24 resize-none`}
            placeholder="What does the maker do next?"
          />
        </div>
        {milestones.length > 0 && (
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Milestone</label>
            <select value={form.milestone} onChange={set('milestone')} className={inputClass}>
              <option value="">(No milestone — loose step)</option>
              {milestones.map((m, idx) => (
                <option key={m.id} value={m.id}>
                  {idx + 1}. {m.title || `Milestone ${idx + 1}`}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.title.trim()} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Adding...' : 'Add Step'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Add Resource Modal ─────────────────────────────────────────── */

export function AddResourceModal({ projectId, steps, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: '',
    url: '',
    resource_type: 'link',
    step: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await createResource(projectId, {
        project: projectId,
        title: form.title,
        url: form.url,
        resource_type: form.resource_type,
        step: form.step || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Resource" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">URL</label>
          <input
            value={form.url}
            onChange={set('url')}
            className={inputClass}
            type="url"
            placeholder="https://..."
            required
            autoFocus
          />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Title (optional)</label>
          <input value={form.title} onChange={set('title')} className={inputClass} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Type</label>
            <select value={form.resource_type} onChange={set('resource_type')} className={inputClass}>
              <option value="link">Link</option>
              <option value="video">Video</option>
              <option value="doc">Document</option>
              <option value="image">Image</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Attach to Step</label>
            <select value={form.step} onChange={set('step')} className={inputClass}>
              <option value="">(Project-level)</option>
              {steps.map((s, idx) => (
                <option key={s.id} value={s.id}>
                  {idx + 1}. {s.title.slice(0, 40)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.url.trim()} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Adding...' : 'Add Resource'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Request Changes Modal ──────────────────────────────────────── */

export function RequestChangesModal({ onClose, onSubmit }) {
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!notes.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(notes.trim());
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <BottomSheet title="Request Changes" onClose={onClose} disabled={submitting}>
      <p className="text-sm text-forge-text-dim">
        Tell the maker what needs to change before you approve this project.
      </p>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="What should they fix or add?"
        autoFocus
        rows={4}
        className="w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text text-base resize-none focus:outline-none focus:border-amber-primary"
      />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onClose}
          disabled={submitting}
          className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={submitting || !notes.trim()}
          className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 disabled:cursor-not-allowed text-black font-semibold py-3 rounded-lg transition-colors"
        >
          {submitting ? 'Sending...' : 'Send'}
        </button>
      </div>
    </BottomSheet>
  );
}
