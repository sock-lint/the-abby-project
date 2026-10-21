import { useRef, useState } from 'react';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import {
  getBadges, getAllSkills, getAllSubjects, updateCategory, updateSubject, updateSkill,
  deleteBadge, deleteCategory, deleteSkill, deleteSubject,
} from '../../api';
import ParchmentCard from '../../components/journal/ParchmentCard';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorAlert from '../../components/ErrorAlert';
import TabButton from '../../components/TabButton';
import { useApi } from '../../hooks/useApi';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import { normalizeList } from '../../utils/api';
import { skillDisplayLabel } from '../../utils/skillLabels';
import CategoryFormModal from './CategoryFormModal';
import SubjectFormModal from './SubjectFormModal';
import SkillFormModal from './SkillFormModal';
import BadgeFormModal from './BadgeFormModal';
import { CheckboxField } from '../../components/form';
import { isTaxonomyAvailable, taxonomyStatus } from '../../utils/taxonomy';

const DELETERS = {
  category: deleteCategory,
  subject: deleteSubject,
  skill: deleteSkill,
  badge: deleteBadge,
};

export default function ManagePanel({ categories, reloadCategories, canManageTaxonomy = false }) {
  const [manageTab, setManageTab] = useState('categories');
  const { data: subjectsData, error: subjectsError, reload: reloadSubjects } = useApi((signal) => getAllSubjects({ includeRetired: true, signal }));
  const { data: skillsData, error: skillsError, reload: reloadSkills } = useApi((signal) => getAllSkills({ includeRetired: true, signal }));
  const { data: badgesData, reload: reloadBadges } = useApi(getBadges);
  const [modal, setModal] = useState(null); // { type, item? }
  const [deleteTarget, setDeleteTarget] = useState(null); // { type, id, label }
  const [error, setError] = useState('');
  const [showRetired, setShowRetired] = useState(false);
  const [retirementTarget, setRetirementTarget] = useState(null);
  const [retirementBusy, setRetirementBusy] = useState(false);
  const retirementPending = useRef(false);
  const [message, setMessage] = useState('');

  const subjects = normalizeList(subjectsData);
  const skills = normalizeList(skillsData).map((skill) => ({
    ...skill,
    category_name: skill.category_name || categories.find((category) => category.id === skill.category)?.name,
  }));
  const badges = normalizeList(badgesData);

  const refreshAll = () => Promise.all([reloadCategories(), reloadSubjects(), reloadSkills(), reloadBadges()]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setError('');
    try {
      await DELETERS[deleteTarget.type](deleteTarget.id);
      setDeleteTarget(null);
      refreshAll();
    } catch (err) {
      setError(err.message);
      setDeleteTarget(null);
    }
  };

  const setRetirement = async (target, retired) => {
    if (retirementPending.current) return;
    retirementPending.current = true;
    setRetirementBusy(true); setError(''); setMessage('');
    try {
      const update = { category: updateCategory, subject: updateSubject, skill: updateSkill }[target.type];
      await update(target.id, { is_retired: retired });
      setRetirementTarget(null);
      setMessage(retired ? `${target.label} retired. Saved progress and existing records remain available.` : `${target.label} restored. A retired category or subject can still keep it unavailable for new choices.`);
      await refreshAll();
    } catch (err) {
      setError(err.message); setRetirementTarget(null);
    } finally {
      retirementPending.current = false; setRetirementBusy(false);
    }
  };

  const tabs = [
    { key: 'categories', label: 'Categories', count: categories.length },
    { key: 'subjects', label: 'Subjects', count: subjects.length },
    { key: 'skills', label: 'Skills', count: skills.length },
    { key: 'badges', label: 'Badges', count: badges.length },
  ];

  const renderRow = (item, type, extra, actionLabel = item.name) => (
    <ParchmentCard key={item.id} className="flex items-center justify-between">
      <div className="flex items-center gap-2 min-w-0">
        {item.icon && <span className="text-lg shrink-0">{item.icon}</span>}
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{item.name}</div>
          {extra && <div className="text-xs text-ink-whisper truncate">{extra}</div>}
          {type !== 'badge' && taxonomyStatus(item, type) && <p className="text-caption text-ink-secondary">{taxonomyStatus(item, type)}</p>}
        </div>
      </div>
      <div className="flex gap-1 shrink-0 ml-2">
        {type !== 'badge' && canManageTaxonomy && <Button size="sm" variant="ghost" disabled={retirementBusy}
          aria-label={`${item.is_retired ? 'Restore' : 'Retire'} ${type} ${actionLabel}`}
          onClick={() => item.is_retired ? setRetirement({ type, id: item.id, label: actionLabel }, false) : setRetirementTarget({ type, id: item.id, label: actionLabel })}>
          {item.is_retired ? 'Restore' : 'Retire'}
        </Button>}
        <IconButton
          onClick={() => setModal({ type, item })}
          variant="ghost"
          size="sm"
          aria-label={`Edit ${type} ${actionLabel}`}
          className="hover:bg-ink-page-shadow/60 text-ink-whisper hover:text-ink-primary"
        >
          <Pencil size={14} />
        </IconButton>
        <IconButton
          onClick={() => setDeleteTarget({ type, id: item.id, label: actionLabel })}
          variant="ghost"
          size="sm"
          aria-label={`Delete ${type} ${actionLabel}`}
          className="hover:bg-ember/20 text-ink-whisper hover:text-ember-deep"
        >
          <Trash2 size={14} />
        </IconButton>
      </div>
    </ParchmentCard>
  );

  return (
    <div className="space-y-4">
      <ErrorAlert message={error || subjectsError || skillsError} onRetry={refreshAll} />
      {message && <p role="status" className="text-body text-ink-secondary">{message}</p>}
      {manageTab !== 'badges' && <CheckboxField label="Show retired taxonomy" checked={showRetired} onChange={(event) => setShowRetired(event.target.checked)} />}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {tabs.map((t) => (
          <TabButton key={t.key} active={manageTab === t.key} onClick={() => setManageTab(t.key)}>
            {t.label} ({t.count})
          </TabButton>
        ))}
        <Button
          size="sm"
          onClick={() => setModal({ type: manageTab.replace(/s$/, '') })}
          className="flex items-center gap-1 text-xs shrink-0 ml-auto"
        >
          <Plus size={14} /> Add
        </Button>
      </div>

      <div className="space-y-2">
        {manageTab === 'categories' && categories.filter((entry) => showRetired || isTaxonomyAvailable(entry)).map((c) => renderRow(c, 'category', c.description))}
        {manageTab === 'subjects' && subjects.filter((entry) => showRetired || isTaxonomyAvailable(entry)).map((s) => {
          const cat = categories.find((c) => c.id === s.category);
          return renderRow(s, 'subject', cat ? `${cat.icon} ${cat.name}` : '');
        })}
        {manageTab === 'skills' && skills.filter((entry) => showRetired || isTaxonomyAvailable(entry)).map((s) => {
          const cat = categories.find((c) => c.id === s.category);
          return renderRow(s, 'skill', `${cat?.icon || ''} ${cat?.name || ''} ${s.subject_name ? `/ ${s.subject_name}` : ''}`, skillDisplayLabel(s, skills));
        })}
        {manageTab === 'badges' && badges.map((b) => (
          renderRow(b, 'badge', `${b.criteria_type.replace(/_/g, ' ')} • ${b.rarity}`)
        ))}
      </div>

      {modal?.type === 'category' && (
        <CategoryFormModal
          item={modal.item}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); refreshAll(); }}
        />
      )}
      {modal?.type === 'subject' && (
        <SubjectFormModal
          item={modal.item}
          categories={categories}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); refreshAll(); }}
        />
      )}
      {modal?.type === 'skill' && (
        <SkillFormModal
          item={modal.item}
          categories={categories}
          subjects={subjects}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); refreshAll(); }}
        />
      )}
      {modal?.type === 'badge' && (
        <BadgeFormModal
          item={modal.item}
          subjects={subjects}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); refreshAll(); }}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={`Delete ${deleteTarget.label}?`}
          message="This cannot be undone."
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
      {retirementTarget && <ConfirmDialog title={`Retire ${retirementTarget.label}?`}
        message="Hide this entry from new choices? Saved progress, rewards, and existing records stay available. You can restore it later."
        confirmLabel={retirementBusy ? 'Retiring…' : 'Retire'}
        onConfirm={() => setRetirement(retirementTarget, true)}
        onCancel={() => { if (!retirementBusy) setRetirementTarget(null); }} />}
    </div>
  );
}
