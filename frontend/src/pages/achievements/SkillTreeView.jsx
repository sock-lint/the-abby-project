import { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { getSkillTree } from '../../api';
import CatalogSearch from '../../components/CatalogSearch';
import EmptyState from '../../components/EmptyState';
import Loader from '../../components/Loader';
import TomeShelf from '../../components/atlas/TomeShelf';
import { tierForProgress } from '../../components/atlas/mastery.constants';
import FolioSpread from './FolioSpread';
import SkillDetailSheet from './SkillDetailSheet';
import { XP_THRESHOLDS } from './skillTree.constants';

// Convert a SkillCategory + its summary into the flat spine-descriptor
// shape the lifted TomeShelf expects. The XP math used to live inside
// TomeSpine itself; pulling it up here keeps the spine domain-agnostic so
// Badges / Inventory / Character / Yearbook can each compute their own
// progress signal without dragging the skill-tree XP table along.
function categoryToSpine(category, summary) {
  const level = summary?.level ?? 0;
  const totalXp = summary?.total_xp ?? 0;
  const next = XP_THRESHOLDS[level + 1] ?? XP_THRESHOLDS[6];
  const current = XP_THRESHOLDS[level] ?? 0;
  const span = Math.max(1, next - current);
  const inLevel = Math.max(0, totalXp - current);
  const progressPct = Math.min(100, (inLevel / span) * 100);
  // Cumulative progress across all 6 levels for the foot-band fill — gives
  // a smoother progression across the shelf than per-level XP which resets.
  const shelfPct = Math.min(100, (totalXp / XP_THRESHOLDS[6]) * 100);
  const tier = tierForProgress({ unlocked: true, progressPct, level });
  const ariaLabel = summary
    ? `${category.name}, level ${level}, ${totalXp.toLocaleString()} XP`
    : category.name;
  return {
    id: category.id,
    name: category.name,
    icon: category.icon,
    chip: summary && typeof summary.level === 'number' ? `L${level}` : null,
    progressPct: shelfPct,
    tier,
    ariaLabel,
  };
}

/**
 * SkillTreeView — the Skills tab body. A thin orchestrator: the TomeShelf
 * picks a category, the FolioSpread renders that category's folio, and
 * SkillDetailSheet opens on verse selection.
 */
export default function SkillTreeView({ categories, summaryByCategory }) {
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [tree, setTree] = useState(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState(null);
  const [filter, setFilter] = useState('');

  const shelfItems = useMemo(
    () => (categories || []).map((cat) => categoryToSpine(cat, summaryByCategory?.[cat.id])),
    [categories, summaryByCategory],
  );

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
    } catch {
      setTree(null);
    }
    setTreeLoading(false);
  };

  const q = filter.trim().toLowerCase();
  const filteredTree = useMemo(() => {
    if (!tree || !q) return tree;
    const subjects = (tree.subjects || []).map((subject) => ({
      ...subject,
      skills: (subject.skills || []).filter((s) =>
        (s.name || '').toLowerCase().includes(q)
        || (s.description || '').toLowerCase().includes(q),
      ),
    })).filter((subject) => subject.skills.length > 0);
    return { ...tree, subjects };
  }, [tree, q]);
  const noMatches = tree && q && filteredTree.subjects.length === 0;

  if (!categories?.length) {
    return (
      <EmptyState>
        <div className="text-body font-medium text-ink-primary mb-1">
          No skill categories yet
        </div>
        <div className="text-caption">
          A parent can weave them into the atlas from Manage.
        </div>
      </EmptyState>
    );
  }

  return (
    <div className="space-y-4">
      <TomeShelf
        items={shelfItems}
        activeId={selectedCategory}
        onSelect={loadTree}
        ariaLabel="Skill categories"
      />

      {tree && (
        <CatalogSearch
          value={filter}
          onChange={setFilter}
          placeholder="Search skills in this tome…"
          ariaLabel="Filter skills"
        />
      )}

      {treeLoading && <Loader />}

      {!tree && !treeLoading && (
        <EmptyState>
          <div className="text-body font-medium text-ink-primary mb-1">
            Pull a tome from the shelf
          </div>
          <div className="text-caption">
            Tap a spine above to open its folio and leaf through its skills.
          </div>
        </EmptyState>
      )}

      {noMatches && (
        <EmptyState>
          <div className="text-body font-medium text-ink-primary mb-1">
            No skills match your search
          </div>
          <div className="text-caption">
            Try another word, or clear the filter to see the whole chapter.
          </div>
        </EmptyState>
      )}

      <AnimatePresence mode="wait">
        {tree && !treeLoading && !noMatches && (
          <motion.div
            key={tree.category?.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
          >
            <FolioSpread tree={filteredTree} onSelectSkill={setSelectedSkill} />
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {selectedSkill && (
          <SkillDetailSheet skill={selectedSkill} onClose={() => setSelectedSkill(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}
