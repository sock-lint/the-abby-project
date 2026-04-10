import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import {
  Users, BookTemplate, Pencil, Trash2, Play, DollarSign, Globe,
} from 'lucide-react';
import {
  getChildren, updateChild,
  getTemplates, updateTemplate, deleteTemplate, createProjectFromTemplate,
  getCategories,
} from '../api';
import { useApi } from '../hooks/useApi';
import BottomSheet from '../components/BottomSheet';
import Card from '../components/Card';
import DifficultyStars from '../components/DifficultyStars';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import { inputClass } from '../constants/styles';
import { normalizeList } from '../utils/api';

const tabs = ['Children', 'Templates'];

export default function Manage() {
  const [activeTab, setActiveTab] = useState('Children');

  return (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-bold">Manage</h1>

      <div className="flex gap-1 bg-forge-card rounded-lg p-1 border border-forge-border">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
              activeTab === tab
                ? 'bg-amber-primary/15 text-amber-highlight'
                : 'text-forge-text-dim hover:text-forge-text'
            }`}
          >
            {tab === 'Children' ? <Users size={16} /> : <BookTemplate size={16} />}
            {tab}
          </button>
        ))}
      </div>

      {activeTab === 'Children' && <ChildrenSection />}
      {activeTab === 'Templates' && <TemplatesSection />}
    </div>
  );
}

/* ── Children Section ───────────────────────────────────────────── */

function ChildrenSection() {
  const { data, loading, reload } = useApi(getChildren);
  const [editChild, setEditChild] = useState(null);
  const children = normalizeList(data);

  if (loading) return <Loader />;

  return (
    <div className="space-y-3">
      {children.length === 0 && (
        <EmptyState>No children found. Create child accounts in Django admin.</EmptyState>
      )}
      {children.map((child) => (
        <Card key={child.id} className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-full bg-amber-primary/20 flex items-center justify-center text-amber-highlight text-lg font-bold shrink-0">
            {(child.display_name || child.username || '?')[0].toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-forge-text truncate">
              {child.display_name || child.username}
            </div>
            <div className="text-xs text-forge-text-dim">@{child.username}</div>
            <div className="text-sm text-forge-text-dim flex items-center gap-1 mt-0.5">
              <DollarSign size={12} />{child.hourly_rate}/hr
            </div>
          </div>
          <button
            onClick={() => setEditChild(child)}
            className="bg-forge-muted hover:bg-forge-border text-forge-text px-3 py-2 rounded-lg text-sm font-medium flex items-center gap-1 transition-colors"
          >
            <Pencil size={14} /> Edit
          </button>
        </Card>
      ))}

      <AnimatePresence>
        {editChild && (
          <EditChildModal
            child={editChild}
            onClose={() => setEditChild(null)}
            onSaved={() => { setEditChild(null); reload(); }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function EditChildModal({ child, onClose, onSaved }) {
  const [form, setForm] = useState({
    display_name: child.display_name || '',
    hourly_rate: child.hourly_rate || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await updateChild(child.id, {
        display_name: form.display_name,
        hourly_rate: form.hourly_rate,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title={`Edit ${child.display_name || child.username}`} onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Display Name</label>
          <input value={form.display_name} onChange={set('display_name')} className={inputClass} placeholder={child.username} />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Hourly Rate ($)</label>
          <input value={form.hourly_rate} onChange={set('hourly_rate')} className={inputClass} type="number" step="0.01" min="0" required />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Templates Section ──────────────────────────────────────────── */

function TemplatesSection() {
  const navigate = useNavigate();
  const { data, loading, reload } = useApi(getTemplates);
  const { data: childrenData } = useApi(getChildren);
  const { data: categoriesData } = useApi(getCategories);
  const templates = normalizeList(data);
  const children = normalizeList(childrenData);
  const categories = normalizeList(categoriesData);

  const [useModal, setUseModal] = useState(null);
  const [editModal, setEditModal] = useState(null);

  if (loading) return <Loader />;

  const handleDelete = async (id) => {
    if (!confirm('Delete this template?')) return;
    await deleteTemplate(id);
    reload();
  };

  return (
    <div className="space-y-3">
      {templates.length === 0 && (
        <EmptyState>No templates yet. Save a completed project as a template from the project detail page.</EmptyState>
      )}

      {templates.map((t) => (
        <Card key={t.id} className="space-y-2">
          <div className="flex items-start justify-between">
            <div>
              <div className="font-semibold text-forge-text">{t.title}</div>
              <div className="flex items-center gap-3 text-xs text-forge-text-dim mt-1">
                {t.category && <span>{t.category.icon} {t.category.name}</span>}
                <DifficultyStars difficulty={t.difficulty} />
                {t.milestones?.length > 0 && <span>{t.milestones.length} steps</span>}
                {t.materials?.length > 0 && <span>{t.materials.length} materials</span>}
                {t.is_public && (
                  <span className="flex items-center gap-0.5 text-blue-400">
                    <Globe size={10} /> Public
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                onClick={() => setUseModal(t)}
                className="bg-amber-primary hover:bg-amber-highlight text-black px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1 transition-colors"
              >
                <Play size={12} /> Use
              </button>
              <button
                onClick={() => setEditModal(t)}
                className="bg-forge-muted hover:bg-forge-border text-forge-text px-2 py-1.5 rounded-lg text-xs transition-colors"
              >
                <Pencil size={12} />
              </button>
              <button
                onClick={() => handleDelete(t.id)}
                className="bg-forge-muted hover:bg-red-500/20 text-forge-text-dim hover:text-red-400 px-2 py-1.5 rounded-lg text-xs transition-colors"
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>
          {t.description && (
            <p className="text-xs text-forge-text-dim line-clamp-2">{t.description}</p>
          )}
        </Card>
      ))}

      <AnimatePresence>
        {useModal && (
          <UseTemplateModal
            template={useModal}
            children={children}
            onClose={() => setUseModal(null)}
            onCreated={(project) => {
              setUseModal(null);
              navigate(`/projects/${project.id}`);
            }}
          />
        )}
        {editModal && (
          <EditTemplateModal
            template={editModal}
            categories={categories}
            onClose={() => setEditModal(null)}
            onSaved={() => { setEditModal(null); reload(); }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function UseTemplateModal({ template, children, onClose, onCreated }) {
  const [assignedTo, setAssignedTo] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const handleCreate = async () => {
    setCreating(true);
    setError('');
    try {
      const project = await createProjectFromTemplate(template.id, assignedTo || null);
      onCreated(project);
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <BottomSheet title={`Create from "${template.title}"`} onClose={onClose} disabled={creating}>
      <ErrorAlert message={error} />
      <p className="text-sm text-forge-text-dim">
        This will create a new project with {template.milestones?.length || 0} milestones
        and {template.materials?.length || 0} materials from this template.
      </p>
      <div>
        <label className="block text-xs text-forge-text-dim mb-1">Assign To</label>
        <select value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)} className={inputClass}>
          <option value="">Unassigned</option>
          {children.map((c) => (
            <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
          ))}
        </select>
      </div>
      <div className="flex gap-2">
        <button type="button" onClick={onClose} disabled={creating} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
          Cancel
        </button>
        <button
          type="button"
          onClick={handleCreate}
          disabled={creating}
          className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors"
        >
          {creating ? 'Creating...' : 'Create Project'}
        </button>
      </div>
    </BottomSheet>
  );
}

function EditTemplateModal({ template, categories, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: template.title || '',
    description: template.description || '',
    difficulty: template.difficulty || 2,
    category_id: template.category?.id || '',
    bonus_amount: template.bonus_amount || '0',
    materials_budget: template.materials_budget || '0',
    is_public: template.is_public || false,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await updateTemplate(template.id, {
        ...form,
        difficulty: parseInt(form.difficulty),
        category_id: form.category_id || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Edit Template" onClose={onClose} disabled={saving}>
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
            <label className="block text-xs text-forge-text-dim mb-1">Bonus ($)</label>
            <input value={form.bonus_amount} onChange={set('bonus_amount')} className={inputClass} type="number" step="0.01" min="0" />
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Budget ($)</label>
            <input value={form.materials_budget} onChange={set('materials_budget')} className={inputClass} type="number" step="0.01" min="0" />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm text-forge-text cursor-pointer">
          <input
            type="checkbox"
            checked={form.is_public}
            onChange={(e) => setForm({ ...form, is_public: e.target.checked })}
            className="accent-amber-primary"
          />
          Share publicly (other families can see this template)
        </label>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}
