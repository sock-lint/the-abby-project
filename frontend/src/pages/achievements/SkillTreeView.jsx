import { useEffect, useMemo, useRef, useState } from 'react';
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

const STORAGE_KEY = 'atlas:skill-tree:active-category';

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
  // User-clicked override, seeded from localStorage. The *effective* active
  // category is derived below so the shelf self-heals when a parent renames
  // or deletes the remembered category. Same shape SigilCodex uses on the
  // Badges tab, so both Atlas shelves open on a real folio instead of an
  // empty "pull a tome" state on every visit.
  const [override, setOverride] = useState(() => {
    try {
      return window.localStorage?.getItem(STORAGE_KEY) || null;
    } catch {
      return null;
    }
  });
  // One state cell holding `{ key, tree }` for the fetch that finished, so
  // "is the folio loading?" is derived (key mismatch) rather than a second
  // setState fired synchronously from the effect.
  const [loaded, setLoaded] = useState(null);
  const [selectedSkill, setSelectedSkill] = useState(null);
  const [filter, setFilter] = useState('');
  // Bumped on every spine tap so re-tapping the open tome re-fetches its
  // folio (the old behavior was to collapse it back to an empty state).
  const [reloadNonce, setReloadNonce] = useState(0);
  const requestRef = useRef(0);

  const shelfItems = useMemo(
    () => (categories || []).map((cat) => categoryToSpine(cat, summaryByCategory?.[cat.id])),
    [categories, summaryByCategory],
  );

  // Priority: (1) remembered category that still exists, (2) first category.
  const selectedCategory = useMemo(() => {
    const list = categories || [];
    const remembered = list.find((cat) => String(cat.id) === String(override));
    return remembered?.id ?? list[0]?.id ?? null;
  }, [categories, override]);

  // Selecting is a plain set — tapping the active spine no longer collapses
  // the folio back to the empty state (an easy accidental double-tap).
  const selectCategory = (catId) => {
    setOverride(String(catId));
    setReloadNonce((n) => n + 1);
    try {
      window.localStorage?.setItem(STORAGE_KEY, String(catId));
    } catch {
      // ignore quota / disabled storage
    }
  };

  const loadKey = `${selectedCategory}:${reloadNonce}`;

  useEffect(() => {
    // Only reachable with zero categories, which short-circuits to the
    // "no skill categories yet" empty state below — nothing to fetch.
    if (selectedCategory == null) return;
    const token = ++requestRef.current;
    getSkillTree(selectedCategory)
      .then((data) => {
        if (requestRef.current === token) setLoaded({ key: loadKey, tree: data });
      })
      .catch(() => {
        if (requestRef.current === token) setLoaded({ key: loadKey, tree: null });
      });
  }, [selectedCategory, loadKey]);

  const tree = loaded?.key === loadKey ? loaded.tree : null;
  const treeLoading = selectedCategory != null && loaded?.key !== loadKey;

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
        onSelect={selectCategory}
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

      {/* A tome is always open now, so a missing tree means the folio failed
          to load — not "you haven't picked one yet". */}
      {!tree && !treeLoading && (
        <EmptyState>
          <div className="text-body font-medium text-ink-primary mb-1">
            This tome would not open
          </div>
          <div className="text-caption">
            Tap its spine again to retry, or pull a different one from the shelf.
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
