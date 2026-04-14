import { useState } from 'react';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import {
  getBadges, getSkills, getSubjects,
  deleteBadge, deleteCategory, deleteSkill, deleteSubject,
} from '../../api';
import Card from '../../components/Card';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorAlert from '../../components/ErrorAlert';
import TabButton from '../../components/TabButton';
import { useApi } from '../../hooks/useApi';
import { buttonPrimary } from '../../constants/styles';
import { normalizeList } from '../../utils/api';
import CategoryFormModal from './CategoryFormModal';
import SubjectFormModal from './SubjectFormModal';
import SkillFormModal from './SkillFormModal';
import BadgeFormModal from './BadgeFormModal';

const DELETERS = {
  category: deleteCategory,
  subject: deleteSubject,
  skill: deleteSkill,
  badge: deleteBadge,
};

export default function ManagePanel({ categories, reloadCategories }) {
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

  const refreshAll = () => {
    reloadCategories(); reloadSubjects(); reloadSkills(); reloadBadges();
  };

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
          {extra && <div className="text-xs text-ink-whisper truncate">{extra}</div>}
        </div>
      </div>
      <div className="flex gap-1 shrink-0 ml-2">
        <button
          onClick={() => setModal({ type, item })}
          className="p-1.5 hover:bg-ink-page-shadow/60 rounded text-ink-whisper hover:text-ink-primary"
        >
          <Pencil size={14} />
        </button>
        <button
          onClick={() => setDeleteTarget({ type, id: item.id, label: item.name })}
          className="p-1.5 hover:bg-ember/20 rounded text-ink-whisper hover:text-red-300"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </Card>
  );

  return (
    <div className="space-y-4">
      <ErrorAlert message={error} />
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {tabs.map((t) => (
          <TabButton key={t.key} active={manageTab === t.key} onClick={() => setManageTab(t.key)}>
            {t.label} ({t.count})
          </TabButton>
        ))}
        <button
          onClick={() => setModal({ type: manageTab.replace(/s$/, '') })}
          className={`flex items-center gap-1 px-3 py-1.5 text-xs shrink-0 ml-auto ${buttonPrimary}`}
        >
          <Plus size={14} /> Add
        </button>
      </div>

      <div className="space-y-2">
        {manageTab === 'categories' && categories.map((c) => renderRow(c, 'category', c.description))}
        {manageTab === 'subjects' && subjects.map((s) => {
          const cat = categories.find((c) => c.id === s.category);
          return renderRow(s, 'subject', cat ? `${cat.icon} ${cat.name}` : '');
        })}
        {manageTab === 'skills' && skills.map((s) => {
          const cat = categories.find((c) => c.id === s.category);
          return renderRow(s, 'skill', `${cat?.icon || ''} ${cat?.name || ''} ${s.subject_name ? `/ ${s.subject_name}` : ''}`);
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
    </div>
  );
}
