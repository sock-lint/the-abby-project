import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Lock, Unlock, Plus, Pencil, Trash2, X } from 'lucide-react';
import {
  getAchievementsSummary, getCategories, getSkillTree,
  getBadges, getSubjects, getSkills,
  createCategory, updateCategory, deleteCategory,
  createSubject, updateSubject, deleteSubject,
  createSkill, updateSkill, deleteSkill,
  createBadge, updateBadge, deleteBadge,
} from '../api';
import { useApi, useAuth } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ProgressBar from '../components/ProgressBar';
import TabButton from '../components/TabButton';
import ErrorAlert from '../components/ErrorAlert';
import { RARITY_COLORS } from '../constants/colors';
import { normalizeList } from '../utils/api';

const rarityText = {
  common: 'text-rarity-common',
  uncommon: 'text-rarity-uncommon',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

const XP_THRESHOLDS = { 0: 0, 1: 100, 2: 300, 3: 600, 4: 1000, 5: 1500, 6: 2500 };
const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary'];
const inputClass = 'w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text text-base focus:outline-none focus:border-amber-primary';

const CRITERIA_TYPES = [
  'projects_completed', 'hours_worked', 'category_projects', 'streak_days',
  'first_project', 'first_clock_in', 'materials_under_budget', 'perfect_timecard',
  'skill_level_reached', 'skills_unlocked', 'skill_categories_breadth',
  'subjects_completed', 'hours_in_day', 'photos_uploaded', 'total_earned',
  'days_worked', 'cross_category_unlock',
];

// --- Generic Modal Shell ---
function ModalShell({ title, onClose, children }) {
  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-end md:items-center justify-center"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
    >
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <motion.div
        className="relative w-full md:max-w-lg bg-forge-card border border-forge-border rounded-t-2xl md:rounded-2xl p-5 max-h-[85vh] overflow-y-auto"
        initial={{ y: '100%' }} animate={{ y: 0 }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-heading text-lg font-bold">{title}</h3>
          <button onClick={onClose} className="text-forge-text-dim hover:text-forge-text"><X size={20} /></button>
        </div>
        {children}
      </motion.div>
    </motion.div>
  );
}

// --- Category Form ---
function CategoryFormModal({ item, onClose, onSaved }) {
  const isEdit = !!item;
  const [form, setForm] = useState({
    name: item?.name || '', icon: item?.icon || '', color: item?.color || '#D97706', description: item?.description || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      if (isEdit) await updateCategory(item.id, form);
      else await createCategory(form);
      onSaved();
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  };

  return (
    <ModalShell title={isEdit ? 'Edit Category' : 'New Category'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <div><label className="text-xs text-forge-text-dim mb-1 block">Name</label><input className={inputClass} value={form.name} onChange={set('name')} required /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="text-xs text-forge-text-dim mb-1 block">Icon (emoji)</label><input className={inputClass} value={form.icon} onChange={set('icon')} /></div>
          <div><label className="text-xs text-forge-text-dim mb-1 block">Color</label><input type="color" className="w-full h-10 rounded-lg border border-forge-border bg-forge-bg cursor-pointer" value={form.color} onChange={set('color')} /></div>
        </div>
        <div><label className="text-xs text-forge-text-dim mb-1 block">Description</label><textarea className={inputClass} value={form.description} onChange={set('description')} rows={2} /></div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim">Cancel</button>
          <button type="submit" disabled={saving} className="px-4 py-2 bg-amber-primary hover:bg-amber-highlight text-black text-sm font-semibold rounded-lg disabled:opacity-50">{saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}</button>
        </div>
      </form>
    </ModalShell>
  );
}

// --- Subject Form ---
function SubjectFormModal({ item, categories, onClose, onSaved }) {
  const isEdit = !!item;
  const [form, setForm] = useState({
    name: item?.name || '', category: item?.category || '', icon: item?.icon || '', description: item?.description || '', order: item?.order ?? 0,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      const payload = { ...form, category: parseInt(form.category), order: parseInt(form.order) || 0 };
      if (isEdit) await updateSubject(item.id, payload);
      else await createSubject(payload);
      onSaved();
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  };

  return (
    <ModalShell title={isEdit ? 'Edit Subject' : 'New Subject'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <div><label className="text-xs text-forge-text-dim mb-1 block">Name</label><input className={inputClass} value={form.name} onChange={set('name')} required /></div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Category</label>
            <select className={inputClass} value={form.category} onChange={set('category')} required>
              <option value="">Select...</option>
              {categories.map(c => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
            </select>
          </div>
          <div><label className="text-xs text-forge-text-dim mb-1 block">Icon</label><input className={inputClass} value={form.icon} onChange={set('icon')} /></div>
        </div>
        <div><label className="text-xs text-forge-text-dim mb-1 block">Description</label><textarea className={inputClass} value={form.description} onChange={set('description')} rows={2} /></div>
        <div className="w-1/2"><label className="text-xs text-forge-text-dim mb-1 block">Order</label><input className={inputClass} type="number" value={form.order} onChange={set('order')} /></div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim">Cancel</button>
          <button type="submit" disabled={saving} className="px-4 py-2 bg-amber-primary hover:bg-amber-highlight text-black text-sm font-semibold rounded-lg disabled:opacity-50">{saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}</button>
        </div>
      </form>
    </ModalShell>
  );
}

// --- Skill Form ---
function SkillFormModal({ item, categories, subjects, onClose, onSaved }) {
  const isEdit = !!item;
  const [form, setForm] = useState({
    name: item?.name || '', category: item?.category || '', subject: item?.subject || '',
    icon: item?.icon || '', description: item?.description || '',
    is_locked_by_default: item?.is_locked_by_default ?? false, order: item?.order ?? 0,
    level_names: JSON.stringify(item?.level_names || {}),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm({ ...form, [k]: val });
  };

  const filteredSubjects = subjects.filter(s => !form.category || s.category === parseInt(form.category));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      let level_names = {};
      try { level_names = JSON.parse(form.level_names); } catch { /* keep empty */ }
      const payload = {
        name: form.name, category: parseInt(form.category),
        subject: form.subject ? parseInt(form.subject) : null,
        icon: form.icon, description: form.description,
        is_locked_by_default: form.is_locked_by_default,
        order: parseInt(form.order) || 0, level_names,
      };
      if (isEdit) await updateSkill(item.id, payload);
      else await createSkill(payload);
      onSaved();
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  };

  return (
    <ModalShell title={isEdit ? 'Edit Skill' : 'New Skill'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <div><label className="text-xs text-forge-text-dim mb-1 block">Name</label><input className={inputClass} value={form.name} onChange={set('name')} required /></div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Category</label>
            <select className={inputClass} value={form.category} onChange={set('category')} required>
              <option value="">Select...</option>
              {categories.map(c => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Subject</label>
            <select className={inputClass} value={form.subject} onChange={set('subject')}>
              <option value="">None</option>
              {filteredSubjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="text-xs text-forge-text-dim mb-1 block">Icon</label><input className={inputClass} value={form.icon} onChange={set('icon')} /></div>
          <div><label className="text-xs text-forge-text-dim mb-1 block">Order</label><input className={inputClass} type="number" value={form.order} onChange={set('order')} /></div>
        </div>
        <div><label className="text-xs text-forge-text-dim mb-1 block">Description</label><textarea className={inputClass} value={form.description} onChange={set('description')} rows={2} /></div>
        <div><label className="text-xs text-forge-text-dim mb-1 block">Level Names (JSON)</label><input className={inputClass} value={form.level_names} onChange={set('level_names')} placeholder='{"0":"Novice","1":"Apprentice"}' /></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_locked_by_default} onChange={set('is_locked_by_default')} className="accent-amber-primary" /> Locked by default</label>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim">Cancel</button>
          <button type="submit" disabled={saving} className="px-4 py-2 bg-amber-primary hover:bg-amber-highlight text-black text-sm font-semibold rounded-lg disabled:opacity-50">{saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}</button>
        </div>
      </form>
    </ModalShell>
  );
}

// --- Badge Form ---
function BadgeFormModal({ item, subjects, onClose, onSaved }) {
  const isEdit = !!item;
  const [form, setForm] = useState({
    name: item?.name || '', description: item?.description || '', icon: item?.icon || '',
    subject: item?.subject || '', criteria_type: item?.criteria_type || CRITERIA_TYPES[0],
    criteria_value: JSON.stringify(item?.criteria_value || {}),
    xp_bonus: item?.xp_bonus ?? 0, rarity: item?.rarity || 'common',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      let criteria_value = {};
      try { criteria_value = JSON.parse(form.criteria_value); } catch { /* keep empty */ }
      const payload = {
        name: form.name, description: form.description, icon: form.icon,
        subject: form.subject ? parseInt(form.subject) : null,
        criteria_type: form.criteria_type, criteria_value,
        xp_bonus: parseInt(form.xp_bonus) || 0, rarity: form.rarity,
      };
      if (isEdit) await updateBadge(item.id, payload);
      else await createBadge(payload);
      onSaved();
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  };

  return (
    <ModalShell title={isEdit ? 'Edit Badge' : 'New Badge'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <div><label className="text-xs text-forge-text-dim mb-1 block">Name</label><input className={inputClass} value={form.name} onChange={set('name')} required /></div>
        <div><label className="text-xs text-forge-text-dim mb-1 block">Description</label><textarea className={inputClass} value={form.description} onChange={set('description')} rows={2} required /></div>
        <div className="grid grid-cols-3 gap-3">
          <div><label className="text-xs text-forge-text-dim mb-1 block">Icon</label><input className={inputClass} value={form.icon} onChange={set('icon')} /></div>
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Rarity</label>
            <select className={inputClass} value={form.rarity} onChange={set('rarity')}>
              {RARITIES.map(r => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
            </select>
          </div>
          <div><label className="text-xs text-forge-text-dim mb-1 block">XP Bonus</label><input className={inputClass} type="number" min="0" value={form.xp_bonus} onChange={set('xp_bonus')} /></div>
        </div>
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Subject (optional)</label>
          <select className={inputClass} value={form.subject} onChange={set('subject')}>
            <option value="">None</option>
            {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Criteria Type</label>
          <select className={inputClass} value={form.criteria_type} onChange={set('criteria_type')}>
            {CRITERIA_TYPES.map(ct => <option key={ct} value={ct}>{ct.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Criteria Value (JSON)</label>
          <input className={inputClass} value={form.criteria_value} onChange={set('criteria_value')} placeholder='{"count": 5}' />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim">Cancel</button>
          <button type="submit" disabled={saving} className="px-4 py-2 bg-amber-primary hover:bg-amber-highlight text-black text-sm font-semibold rounded-lg disabled:opacity-50">{saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}</button>
        </div>
      </form>
    </ModalShell>
  );
}

// --- Delete Confirm ---
function DeleteConfirmModal({ label, onClose, onConfirm }) {
  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
    >
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <motion.div className="relative bg-forge-card border border-forge-border rounded-2xl p-5 max-w-sm w-full mx-4" initial={{ scale: 0.9 }} animate={{ scale: 1 }}>
        <h3 className="font-heading font-bold mb-2">Delete {label}?</h3>
        <p className="text-sm text-forge-text-dim mb-4">This cannot be undone.</p>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim">Cancel</button>
          <button onClick={onConfirm} className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-300 text-sm font-semibold rounded-lg border border-red-500/30">Delete</button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// --- Management Panel ---
function ManagePanel({ categories, reloadCategories }) {
  const [manageTab, setManageTab] = useState('categories');
  const { data: subjectsData, reload: reloadSubjects } = useApi(getSubjects);
  const { data: skillsData, reload: reloadSkills } = useApi(getSkills);
  const { data: badgesData, reload: reloadBadges } = useApi(getBadges);
  const [modal, setModal] = useState(null); // { type, item? }
  const [deleteTarget, setDeleteTarget] = useState(null); // { type, id, label }
  const [error, setError] = useState('');

  const subjects = normalizeList(subjectsData);
  const skills = normalizeList(skillsData);
  const badges = normalizeList(badgesData);

  const refreshAll = () => { reloadCategories(); reloadSubjects(); reloadSkills(); reloadBadges(); };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setError('');
    try {
      if (deleteTarget.type === 'category') await deleteCategory(deleteTarget.id);
      else if (deleteTarget.type === 'subject') await deleteSubject(deleteTarget.id);
      else if (deleteTarget.type === 'skill') await deleteSkill(deleteTarget.id);
      else if (deleteTarget.type === 'badge') await deleteBadge(deleteTarget.id);
      setDeleteTarget(null);
      refreshAll();
    } catch (err) { setError(err.message); setDeleteTarget(null); }
  };

  const tabs = [
    { key: 'categories', label: 'Categories', count: categories.length },
    { key: 'subjects', label: 'Subjects', count: subjects.length },
    { key: 'skills', label: 'Skills', count: skills.length },
    { key: 'badges', label: 'Badges', count: badges.length },
  ];

  const renderRow = (item, type, extra) => (
    <Card key={item.id} className="flex items-center justify-between">
      <div className="flex items-center gap-2 min-w-0">
        {item.icon && <span className="text-lg shrink-0">{item.icon}</span>}
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{item.name}</div>
          {extra && <div className="text-xs text-forge-text-dim truncate">{extra}</div>}
        </div>
      </div>
      <div className="flex gap-1 shrink-0 ml-2">
        <button onClick={() => setModal({ type, item })} className="p-1.5 hover:bg-forge-muted rounded text-forge-text-dim hover:text-forge-text"><Pencil size={14} /></button>
        <button onClick={() => setDeleteTarget({ type, id: item.id, label: item.name })} className="p-1.5 hover:bg-red-500/20 rounded text-forge-text-dim hover:text-red-300"><Trash2 size={14} /></button>
      </div>
    </Card>
  );

  return (
    <div className="space-y-4">
      <ErrorAlert message={error} />
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {tabs.map(t => (
          <TabButton key={t.key} active={manageTab === t.key} onClick={() => setManageTab(t.key)}>
            {t.label} ({t.count})
          </TabButton>
        ))}
        <button
          onClick={() => setModal({ type: manageTab.replace(/s$/, '') })}
          className="flex items-center gap-1 bg-amber-primary hover:bg-amber-highlight text-black text-xs font-semibold px-3 py-1.5 rounded-lg shrink-0 ml-auto"
        >
          <Plus size={14} /> Add
        </button>
      </div>

      <div className="space-y-2">
        {manageTab === 'categories' && categories.map(c => renderRow(c, 'category', c.description))}
        {manageTab === 'subjects' && subjects.map(s => {
          const cat = categories.find(c => c.id === s.category);
          return renderRow(s, 'subject', cat ? `${cat.icon} ${cat.name}` : '');
        })}
        {manageTab === 'skills' && skills.map(s => {
          const cat = categories.find(c => c.id === s.category);
          return renderRow(s, 'skill', `${cat?.icon || ''} ${cat?.name || ''} ${s.subject_name ? `/ ${s.subject_name}` : ''}`);
        })}
        {manageTab === 'badges' && badges.map(b => renderRow(b, 'badge', `${b.criteria_type.replace(/_/g, ' ')} • ${b.rarity}`))}
      </div>

      <AnimatePresence>
        {modal?.type === 'category' && (
          <CategoryFormModal item={modal.item} onClose={() => setModal(null)} onSaved={() => { setModal(null); refreshAll(); }} />
        )}
        {modal?.type === 'subject' && (
          <SubjectFormModal item={modal.item} categories={categories} onClose={() => setModal(null)} onSaved={() => { setModal(null); refreshAll(); }} />
        )}
        {modal?.type === 'skill' && (
          <SkillFormModal item={modal.item} categories={categories} subjects={subjects} onClose={() => setModal(null)} onSaved={() => { setModal(null); refreshAll(); }} />
        )}
        {modal?.type === 'badge' && (
          <BadgeFormModal item={modal.item} subjects={subjects} onClose={() => setModal(null)} onSaved={() => { setModal(null); refreshAll(); }} />
        )}
        {deleteTarget && (
          <DeleteConfirmModal label={deleteTarget.label} onClose={() => setDeleteTarget(null)} onConfirm={handleDelete} />
        )}
      </AnimatePresence>
    </div>
  );
}

// --- Main Page ---
export default function Achievements() {
  const { user } = useAuth();
  const isParent = user?.role === 'parent';
  const { data: summary, loading } = useApi(getAchievementsSummary);
  const { data: categoriesData, reload: reloadCategories } = useApi(getCategories);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [tree, setTree] = useState(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [topTab, setTopTab] = useState('view');

  const categories = normalizeList(categoriesData);

  const loadTree = async (catId) => {
    if (selectedCategory === catId) {
      setSelectedCategory(null);
      setTree(null);
      return;
    }
    setSelectedCategory(catId);
    setTreeLoading(true);
    try {
      const data = await getSkillTree(catId);
      setTree(data);
    } catch { setTree(null); }
    setTreeLoading(false);
  };

  if (loading) return <Loader />;
  if (!summary) return null;

  const earnedBadges = summary.badges_earned || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold">Achievements</h1>
        {isParent && (
          <div className="flex gap-2">
            <TabButton active={topTab === 'view'} onClick={() => setTopTab('view')}>View</TabButton>
            <TabButton active={topTab === 'manage'} onClick={() => setTopTab('manage')}>Manage</TabButton>
          </div>
        )}
      </div>

      {topTab === 'manage' && isParent ? (
        <ManagePanel categories={categories} reloadCategories={reloadCategories} />
      ) : (
        <>
          {/* Badge Collection */}
          <div>
            <h2 className="font-heading text-lg font-bold mb-3">
              Badges ({earnedBadges.length}/{summary.total_badges})
            </h2>
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
              {earnedBadges.map((ub, i) => (
                <motion.div
                  key={ub.id}
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: i * 0.03 }}
                >
                  <Card className={`text-center ${RARITY_COLORS[ub.badge.rarity]}`}>
                    <div className="text-3xl mb-1">{ub.badge.icon}</div>
                    <div className="text-xs font-medium leading-tight">{ub.badge.name}</div>
                    <div className={`text-[10px] capitalize ${rarityText[ub.badge.rarity]}`}>{ub.badge.rarity}</div>
                  </Card>
                </motion.div>
              ))}
            </div>
          </div>

          {/* Skill Tree */}
          <div>
            <h2 className="font-heading text-lg font-bold mb-3">Skill Tree</h2>
            <div className="flex gap-2 overflow-x-auto pb-2 mb-4">
              {categories.map((cat) => (
                <TabButton
                  key={cat.id}
                  active={selectedCategory === cat.id}
                  onClick={() => loadTree(cat.id)}
                  className="shrink-0"
                >
                  <span className="flex items-center gap-1.5">
                    <span>{cat.icon}</span>
                    <span>{cat.name}</span>
                  </span>
                </TabButton>
              ))}
            </div>

            {treeLoading && <Loader />}

            {tree && !treeLoading && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                <Card className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">{tree.category.icon}</span>
                    <div>
                      <div className="font-bold">{tree.category.name}</div>
                      <div className="text-xs text-forge-text-dim">
                        Level {tree.summary.level} | {tree.summary.total_xp} XP
                      </div>
                    </div>
                  </div>
                </Card>

                {(tree.subjects || [{ id: null, name: '', skills: tree.skills, summary: tree.summary }]).map((subject) => (
                  <div key={subject.id ?? 'flat'} className="space-y-2">
                    {subject.name && (
                      <div className="flex items-center justify-between px-1">
                        <div className="flex items-center gap-2">
                          {subject.icon && <span>{subject.icon}</span>}
                          <span className="font-heading text-sm font-bold text-forge-text">{subject.name}</span>
                        </div>
                        {subject.summary && (
                          <span className="text-xs text-forge-text-dim">
                            L{subject.summary.level} · {subject.summary.total_xp} XP
                          </span>
                        )}
                      </div>
                    )}
                    <div className="grid md:grid-cols-2 gap-3">
                      {subject.skills.map((skill) => {
                    const nextThreshold = XP_THRESHOLDS[skill.level + 1] || XP_THRESHOLDS[6];
                    const currentThreshold = XP_THRESHOLDS[skill.level] || 0;
                    const progress = nextThreshold > currentThreshold
                      ? ((skill.xp_points - currentThreshold) / (nextThreshold - currentThreshold)) * 100
                      : 100;
                    const levelName = skill.level_names[String(skill.level)] || '';

                    return (
                      <motion.div key={skill.id} layout>
                        <Card className={`${!skill.unlocked ? 'opacity-40' : ''}`}>
                          <div className="flex items-center gap-3 mb-2">
                            <div className="text-2xl">{skill.icon}</div>
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-sm">{skill.name}</span>
                                {!skill.unlocked && <Lock size={12} className="text-forge-text-dim" />}
                                {skill.unlocked && skill.is_locked_by_default && (
                                  <Unlock size={12} className="text-amber-highlight" />
                                )}
                              </div>
                              <div className="text-xs text-forge-text-dim">
                                {skill.unlocked
                                  ? `Level ${skill.level}${levelName ? ` — ${levelName}` : ''}`
                                  : 'Locked'
                                }
                              </div>
                            </div>
                            <div className="font-heading text-sm font-bold text-forge-text-dim">
                              L{skill.level}
                            </div>
                          </div>
                          {skill.unlocked && (
                            <div>
                              <div className="flex justify-between text-xs text-forge-text-dim mb-1">
                                <span>{skill.xp_points} XP</span>
                                <span>{nextThreshold} XP</span>
                              </div>
                              <ProgressBar value={Math.min(100, progress)} />
                            </div>
                          )}
                          {!skill.unlocked && skill.prerequisites?.length > 0 && (
                            <div className="text-xs text-forge-text-dim mt-1">
                              Requires: {skill.prerequisites.map(p =>
                                `${p.skill_name} L${p.required_level}${p.met ? ' ✓' : ''}`
                              ).join(', ')}
                            </div>
                          )}
                        </Card>
                      </motion.div>
                    );
                      })}
                    </div>
                  </div>
                ))}
              </motion.div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
