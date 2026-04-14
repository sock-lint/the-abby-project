import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import {
  Users, BookTemplate, Pencil, Trash2, Play, DollarSign, Globe, Link2, Unlink,
} from 'lucide-react';
import {
  getChildren, updateChild,
  getTemplates, updateTemplate, deleteTemplate, createProjectFromTemplate,
  getCategories, getGoogleAuthUrl, unlinkGoogleAccount,
} from '../api';
import { useApi } from '../hooks/useApi';
import { useFormState } from '../hooks/useFormState';
import BottomSheet from '../components/BottomSheet';
import Card from '../components/Card';
import ConfirmDialog from '../components/ConfirmDialog';
import StarRating from '../components/StarRating';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import { buttonPrimary, buttonSecondary, inputClass } from '../constants/styles';
import { normalizeList } from '../utils/api';

const tabs = ['Children', 'Templates'];

export default function Manage() {
  const [activeTab, setActiveTab] = useState('Children');

  return (
    <div className="space-y-6">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          stewardship · the keeper's ledger
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Manage
        </h1>
      </header>

      <div className="flex gap-1 bg-ink-page-aged rounded-lg p-1 border border-ink-page-shadow">
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-2 rounded-md font-display text-sm transition-colors flex items-center justify-center gap-2 ${
              activeTab === tab
                ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
                : 'text-ink-secondary hover:text-ink-primary'
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
          <div className="w-12 h-12 rounded-full bg-sheikah-teal/20 flex items-center justify-center text-sheikah-teal-deep text-lg font-bold shrink-0">
            {(child.display_name || child.username || '?')[0].toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-ink-primary truncate">
              {child.display_name || child.username}
            </div>
            <div className="text-xs text-ink-whisper">@{child.username}</div>
            <div className="text-sm text-ink-whisper flex items-center gap-1 mt-0.5">
              <DollarSign size={12} />{child.hourly_rate}/hr
              {child.google_linked && (
                <span className="ml-2 text-xs text-moss flex items-center gap-0.5">
                  <Link2 size={10} /> Google
                </span>
              )}
            </div>
          </div>
          <button
            onClick={() => setEditChild(child)}
            className={`flex items-center gap-1 px-3 py-2 text-sm ${buttonSecondary}`}
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
  const { form, set, saving, setSaving, error, setError } = useFormState({
    display_name: child.display_name || '',
    hourly_rate: child.hourly_rate || '',
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
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

  const handleLinkGoogle = async () => {
    try {
      const data = await getGoogleAuthUrl(child.id);
      if (data?.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch {
      setError('Could not start Google linking.');
    }
  };

  const handleUnlinkGoogle = async () => {
    try {
      await unlinkGoogleAccount(child.id);
      onSaved();
    } catch {
      setError('Failed to unlink Google account.');
    }
  };

  return (
    <BottomSheet title={`Edit ${child.display_name || child.username}`} onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-ink-whisper mb-1">Display Name</label>
          <input value={form.display_name} onChange={onField('display_name')} className={inputClass} placeholder={child.username} />
        </div>
        <div>
          <label className="block text-xs text-ink-whisper mb-1">Hourly Rate ($)</label>
          <input value={form.hourly_rate} onChange={onField('hourly_rate')} className={inputClass} type="number" step="0.01" min="0" required />
        </div>
        <div>
          <label className="block text-xs text-ink-whisper mb-1">Google Account</label>
          {child.google_linked ? (
            <button
              type="button"
              onClick={handleUnlinkGoogle}
              className="flex items-center gap-2 text-sm text-ember-deep hover:text-red-300 transition-colors"
            >
              <Unlink size={14} /> Unlink Google Account
            </button>
          ) : (
            <button
              type="button"
              onClick={handleLinkGoogle}
              className="flex items-center gap-2 text-sm text-ink-whisper hover:text-sheikah-teal-deep transition-colors"
            >
              <Link2 size={14} /> Link Google Account
            </button>
          )}
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className={`flex-1 py-3 ${buttonSecondary}`}>
            Cancel
          </button>
          <button type="submit" disabled={saving} className={`flex-1 py-3 ${buttonPrimary}`}>
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
  const [deleteId, setDeleteId] = useState(null);

  if (loading) return <Loader />;

  const confirmDelete = async () => {
    const id = deleteId;
    setDeleteId(null);
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
              <div className="font-semibold text-ink-primary">{t.title}</div>
              <div className="flex items-center gap-3 text-xs text-ink-whisper mt-1">
                {t.category && <span>{t.category.icon} {t.category.name}</span>}
                <StarRating value={t.difficulty} />
                {t.milestones?.length > 0 && <span>{t.milestones.length} milestones</span>}
                {t.steps?.length > 0 && <span>{t.steps.length} steps</span>}
                {t.materials?.length > 0 && <span>{t.materials.length} materials</span>}
                {t.is_public && (
                  <span className="flex items-center gap-0.5 text-sheikah-teal-deep">
                    <Globe size={10} /> Public
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                onClick={() => setUseModal(t)}
                className={`flex items-center gap-1 px-3 py-1.5 text-xs ${buttonPrimary}`}
              >
                <Play size={12} /> Use
              </button>
              <button
                onClick={() => setEditModal(t)}
                className={`px-2 py-1.5 text-xs ${buttonSecondary}`}
              >
                <Pencil size={12} />
              </button>
              <button
                onClick={() => setDeleteId(t.id)}
                className="bg-ink-page-shadow/60 hover:bg-ember/20 text-ink-whisper hover:text-ember-deep px-2 py-1.5 rounded-lg text-xs transition-colors"
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>
          {t.description && (
            <p className="text-xs text-ink-whisper line-clamp-2">{t.description}</p>
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

      {deleteId && (
        <ConfirmDialog
          title="Delete this template?"
          message="This cannot be undone."
          onConfirm={confirmDelete}
          onCancel={() => setDeleteId(null)}
        />
      )}
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
      <p className="text-sm text-ink-whisper">
        This will create a new project with {template.milestones?.length || 0} milestones
        and {template.materials?.length || 0} materials from this template.
      </p>
      <div>
        <label className="block text-xs text-ink-whisper mb-1">Assign To</label>
        <select value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)} className={inputClass}>
          <option value="">Unassigned</option>
          {children.map((c) => (
            <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
          ))}
        </select>
      </div>
      <div className="flex gap-2">
        <button type="button" onClick={onClose} disabled={creating} className={`flex-1 py-3 ${buttonSecondary}`}>
          Cancel
        </button>
        <button
          type="button"
          onClick={handleCreate}
          disabled={creating}
          className={`flex-1 py-3 ${buttonPrimary}`}
        >
          {creating ? 'Creating...' : 'Create Project'}
        </button>
      </div>
    </BottomSheet>
  );
}

function EditTemplateModal({ template, categories, onClose, onSaved }) {
  const { form, set, saving, setSaving, error, setError } = useFormState({
    title: template.title || '',
    description: template.description || '',
    difficulty: template.difficulty || 2,
    category_id: template.category?.id || '',
    bonus_amount: template.bonus_amount || '0',
    materials_budget: template.materials_budget || '0',
    is_public: template.is_public || false,
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
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
          <label className="block text-xs text-ink-whisper mb-1">Title</label>
          <input value={form.title} onChange={onField('title')} className={inputClass} required />
        </div>
        <div>
          <label className="block text-xs text-ink-whisper mb-1">Description</label>
          <textarea value={form.description} onChange={onField('description')} className={`${inputClass} h-20 resize-none`} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Category</label>
            <select value={form.category_id} onChange={onField('category_id')} className={inputClass}>
              <option value="">None</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Difficulty</label>
            <select value={form.difficulty} onChange={onField('difficulty')} className={inputClass}>
              {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>)}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Bonus ($)</label>
            <input value={form.bonus_amount} onChange={onField('bonus_amount')} className={inputClass} type="number" step="0.01" min="0" />
          </div>
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Budget ($)</label>
            <input value={form.materials_budget} onChange={onField('materials_budget')} className={inputClass} type="number" step="0.01" min="0" />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-primary cursor-pointer">
          <input
            type="checkbox"
            checked={form.is_public}
            onChange={(e) => set({ is_public: e.target.checked })}
            className="accent-amber-primary"
          />
          Share publicly (other families can see this template)
        </label>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className={`flex-1 py-3 ${buttonSecondary}`}>
            Cancel
          </button>
          <button type="submit" disabled={saving} className={`flex-1 py-3 ${buttonPrimary}`}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}
