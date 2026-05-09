import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import {
  Users, UserPlus, BookTemplate, BookOpen, ScrollText, Pencil, Trash2, Play, DollarSign, Globe, Link2, Unlink,
  TestTubeDiagonal,
} from 'lucide-react';
import {
  getChildren, createChild, updateChild,
  getTemplates, updateTemplate, deleteTemplate, createProjectFromTemplate,
  getCategories, getGoogleAuthUrl, unlinkGoogleAccount,
  devToolsPing,
} from '../api';
import CodexSection from './manage/CodexSection';
import GuideSection from './manage/GuideSection';
import TestSection from './manage/TestSection';
import { useApi } from '../hooks/useApi';
import { useFormState } from '../hooks/useFormState';
import BottomSheet from '../components/BottomSheet';
import ParchmentCard from '../components/journal/ParchmentCard';
import ConfirmDialog from '../components/ConfirmDialog';
import StarRating from '../components/StarRating';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import Button from '../components/Button';
import IconButton from '../components/IconButton';
import { TextField, SelectField, TextAreaField } from '../components/form';
import { normalizeList } from '../utils/api';

const BASE_TABS = ['Children', 'Templates', 'Codex', 'Guide'];

const TAB_ICONS = {
  Children: Users,
  Templates: BookTemplate,
  Codex: BookOpen,
  Guide: ScrollText,
  Test: TestTubeDiagonal,
};

export default function Manage() {
  const [activeTab, setActiveTab] = useState('Children');
  // The Test tab is staff-parent + DEBUG/DEV_TOOLS_ENABLED only. The
  // backend gate is the source of truth — we ping it once on mount;
  // 200 → tab visible, anything else → tab hidden. Anonymous + child +
  // signup-created parents (is_staff=False) all hit 401/403 here and
  // the tab never appears, even on a deployment that ships with
  // DEV_TOOLS_ENABLED=true.
  const [devToolsEnabled, setDevToolsEnabled] = useState(false);
  useEffect(() => {
    let alive = true;
    devToolsPing()
      .then(() => { if (alive) setDevToolsEnabled(true); })
      .catch(() => { if (alive) setDevToolsEnabled(false); });
    return () => { alive = false; };
  }, []);
  const tabs = devToolsEnabled ? [...BASE_TABS, 'Test'] : BASE_TABS;

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
        {tabs.map((tab) => {
          const Icon = TAB_ICONS[tab];
          return (
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
              {Icon && <Icon size={16} />}
              {tab}
            </button>
          );
        })}
      </div>

      {activeTab === 'Children' && <ChildrenSection />}
      {activeTab === 'Templates' && <TemplatesSection />}
      {activeTab === 'Codex' && <CodexSection />}
      {activeTab === 'Guide' && <GuideSection />}
      {activeTab === 'Test' && devToolsEnabled && <TestSection />}
    </div>
  );
}

/* ── Children Section ───────────────────────────────────────────── */

function ChildrenSection() {
  const { data, loading, reload } = useApi(getChildren);
  const [editChild, setEditChild] = useState(null);
  const [creating, setCreating] = useState(false);
  const children = normalizeList(data);

  if (loading) return <Loader />;

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button onClick={() => setCreating(true)} className="flex items-center gap-1">
          <UserPlus size={14} /> New child
        </Button>
      </div>
      {children.length === 0 && (
        <EmptyState>No children yet — tap <span className="font-semibold">New child</span> to add one.</EmptyState>
      )}
      {children.map((child) => (
        <ParchmentCard key={child.id} className="flex items-center gap-4">
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
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setEditChild(child)}
            className="flex items-center gap-1"
          >
            <Pencil size={14} /> Edit
          </Button>
        </ParchmentCard>
      ))}

      <AnimatePresence>
        {editChild && (
          <EditChildModal
            child={editChild}
            onClose={() => setEditChild(null)}
            onSaved={() => { setEditChild(null); reload(); }}
          />
        )}
        {creating && (
          <CreateChildModal
            onClose={() => setCreating(false)}
            onCreated={() => { setCreating(false); reload(); }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function CreateChildModal({ onClose, onCreated }) {
  const { form, set, saving, setSaving, error, setError } = useFormState({
    username: '',
    password: '',
    display_name: '',
    hourly_rate: '8.00',
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createChild({
        username: form.username.trim(),
        password: form.password,
        display_name: form.display_name.trim(),
        hourly_rate: form.hourly_rate,
      });
      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="New child" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <TextField
          label="Sign-in name"
          value={form.username}
          onChange={onField('username')}
          required
          autoComplete="off"
        />
        <TextField
          label="Display name"
          value={form.display_name}
          onChange={onField('display_name')}
          placeholder={form.username}
        />
        <TextField
          label="Secret word"
          type="password"
          value={form.password}
          onChange={onField('password')}
          required
          autoComplete="new-password"
        />
        <TextField
          label="Hourly rate ($)"
          value={form.hourly_rate}
          onChange={onField('hourly_rate')}
          type="number"
          step="0.01"
          min="0"
          required
        />
        <div className="flex gap-2 justify-end pt-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? 'Creating…' : 'Create child'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}

function EditChildModal({ child, onClose, onSaved }) {
  const { form, set, saving, setSaving, error, setError } = useFormState({
    display_name: child.display_name || '',
    hourly_rate: child.hourly_rate || '',
    date_of_birth: child.date_of_birth || '',
    grade_entry_year: child.grade_entry_year ?? '',
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
        date_of_birth: form.date_of_birth || null,
        grade_entry_year: form.grade_entry_year !== '' ? Number(form.grade_entry_year) : null,
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
        <TextField label="Display Name" value={form.display_name} onChange={onField('display_name')} placeholder={child.username} />
        <TextField label="Hourly Rate ($)" value={form.hourly_rate} onChange={onField('hourly_rate')} type="number" step="0.01" min="0" required />
        <TextField
          type="date"
          label="Date of birth"
          value={form.date_of_birth}
          onChange={onField('date_of_birth')}
          helpText="Used for birthday celebrations and chapter rollovers."
        />
        <SelectField
          label="Grade entry year"
          value={form.grade_entry_year}
          onChange={(e) =>
            set({ grade_entry_year: e.target.value ? Number(e.target.value) : '' })
          }
          helpText="Year she entered 9th grade (August)."
        >
          <option value="">—</option>
          {Array.from({ length: 9 }, (_, i) => new Date().getFullYear() - 4 + i).map((year) => (
            <option key={year} value={year}>{year} (9th grade Aug {year})</option>
          ))}
        </SelectField>
        <div>
          <label className="block text-xs text-ink-whisper mb-1">Google Account</label>
          {child.google_linked ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleUnlinkGoogle}
              className="!text-ember-deep hover:!text-red-300 inline-flex items-center gap-2"
            >
              <Unlink size={14} /> Unlink Google Account
            </Button>
          ) : (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleLinkGoogle}
              className="!text-ink-whisper hover:!text-sheikah-teal-deep inline-flex items-center gap-2"
            >
              <Link2 size={14} /> Link Google Account
            </Button>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose} disabled={saving} className="flex-1">
            Cancel
          </Button>
          <Button type="submit" disabled={saving} className="flex-1">
            {saving ? 'Saving...' : 'Save'}
          </Button>
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
        <ParchmentCard key={t.id} className="space-y-2">
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
              <Button
                size="sm"
                onClick={() => setUseModal(t)}
                className="flex items-center gap-1 text-xs"
              >
                <Play size={12} /> Use
              </Button>
              <IconButton
                variant="secondary"
                size="sm"
                onClick={() => setEditModal(t)}
                aria-label="Edit template"
              >
                <Pencil size={12} />
              </IconButton>
              <IconButton
                onClick={() => setDeleteId(t.id)}
                variant="ghost"
                size="sm"
                aria-label="Delete template"
                className="bg-ink-page-shadow/60 hover:bg-ember/20 text-ink-whisper hover:text-ember-deep text-xs"
              >
                <Trash2 size={12} />
              </IconButton>
            </div>
          </div>
          {t.description && (
            <p className="text-xs text-ink-whisper line-clamp-2">{t.description}</p>
          )}
        </ParchmentCard>
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
      <SelectField label="Assign To" value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)}>
        <option value="">Unassigned</option>
        {children.map((c) => (
          <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
        ))}
      </SelectField>
      <div className="flex gap-2">
        <Button variant="secondary" onClick={onClose} disabled={creating} className="flex-1">
          Cancel
        </Button>
        <Button onClick={handleCreate} disabled={creating} className="flex-1">
          {creating ? 'Creating...' : 'Create Project'}
        </Button>
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
        <TextField label="Title" value={form.title} onChange={onField('title')} required />
        <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={3} />
        <div className="grid grid-cols-2 gap-3">
          <SelectField label="Category" value={form.category_id} onChange={onField('category_id')}>
            <option value="">None</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
          </SelectField>
          <SelectField label="Difficulty" value={form.difficulty} onChange={onField('difficulty')}>
            {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>)}
          </SelectField>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Bonus ($)" value={form.bonus_amount} onChange={onField('bonus_amount')} type="number" step="0.01" min="0" />
          <TextField label="Budget ($)" value={form.materials_budget} onChange={onField('materials_budget')} type="number" step="0.01" min="0" />
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
          <Button variant="secondary" onClick={onClose} disabled={saving} className="flex-1">
            Cancel
          </Button>
          <Button type="submit" disabled={saving} className="flex-1">
            {saving ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}
