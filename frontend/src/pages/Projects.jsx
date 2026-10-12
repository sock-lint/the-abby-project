import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import useSearchParamState from '../hooks/useSearchParamState';
import { motion } from 'framer-motion';
import { Plus, Sparkles } from 'lucide-react';
import { getProjects, getProjectSuggestions, getChildren } from '../api';
import { useApi } from '../hooks/useApi';
import StarRating from '../components/StarRating';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import CatalogSearch from '../components/CatalogSearch';
import Loader from '../components/Loader';
import StatusBadge from '../components/StatusBadge';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import ChapterRubric from '../components/atlas/ChapterRubric';
import { InkwellIcon } from '../components/icons/JournalIcons';
import { useRole } from '../hooks/useRole';
import Button from '../components/Button';
import AddToCalendar from '../components/AddToCalendar';
import { SelectField } from '../components/form';
import { normalizeList } from '../utils/api';
import { formatDate } from '../utils/format';
import { staggerChildren, staggerItem } from '../motion/variants';
import QuestFolio from './quests/QuestFolio';
import { buildRarityCounts, difficultyToRarity } from './quests/quests.constants';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'in_review', label: 'In review' },
  { value: 'completed', label: 'Completed' },
];

const TYPE_OPTIONS = [
  { value: '', label: 'All types' },
  { value: 'required', label: 'Required' },
  { value: 'bounty', label: 'Optional project' },
];

// Order matters: chapters in the recto read in-progress → in-review →
// drafts → done, matching the natural narrative of a venture's life.
const STATUS_RUBRICS = [
  { key: 'in_progress', label: 'In Progress' },
  { key: 'in_review', label: 'In Review' },
  { key: 'draft', label: 'Drafts' },
  { key: 'completed', label: 'Completed' },
];

export default function Projects() {
  const { isParent } = useRole();
  const { data, loading, error, reload } = useApi(getProjects);
  const { data: suggestions } = useApi(getProjectSuggestions);
  const { data: childrenData } = useApi(getChildren);
  const navigate = useNavigate();

  const [, setSearchParams] = useSearchParams();
  const [statusFilter, setStatusFilter] = useSearchParamState('status', '');
  const [typeFilter, setTypeFilter] = useSearchParamState('type', '');
  const [childFilter, setChildFilter] = useSearchParamState('child', '');
  const [search, setSearch] = useState('');

  const clearAllFilters = () => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete('status');
      next.delete('type');
      next.delete('child');
      return next;
    }, { replace: true });
    setSearch('');
  };

  const allProjects = normalizeList(data);
  const children = normalizeList(childrenData);

  const projects = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allProjects.filter((p) => {
      if (statusFilter && p.status !== statusFilter) return false;
      if (typeFilter && p.payment_kind !== typeFilter) return false;
      if (childFilter) {
        if (childFilter === 'unassigned' && p.assigned_to) return false;
        if (childFilter !== 'unassigned' && p.assigned_to?.id !== parseInt(childFilter)) return false;
      }
      if (q) {
        const title = (p.title || '').toLowerCase();
        const desc = (p.description || '').toLowerCase();
        if (!title.includes(q) && !desc.includes(q)) return false;
      }
      return true;
    });
  }, [allProjects, statusFilter, typeFilter, childFilter, search]);

  const groupedProjects = useMemo(() => {
    const seen = new Map(STATUS_RUBRICS.map((r) => [r.key, []]));
    const fallback = [];
    for (const p of projects) {
      if (seen.has(p.status)) seen.get(p.status).push(p);
      else fallback.push(p);
    }
    // Append fallback (unknown statuses) under In Progress so they don't
    // vanish; matches the legacy single-grid behavior for safety.
    if (fallback.length) seen.get('in_progress').push(...fallback);
    return seen;
  }, [projects]);

  // Verso stats describe the chapter as a whole — unfiltered counts so
  // searching for "volcano" doesn't make the verso lie about the page.
  const inProgressCount = useMemo(
    () => allProjects.filter((p) => p.status === 'in_progress').length,
    [allProjects],
  );
  const completedCount = useMemo(
    () => allProjects.filter((p) => p.status === 'completed').length,
    [allProjects],
  );
  const totalCount = allProjects.length;
  const progressPct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;
  const rarityCounts = useMemo(
    () => buildRarityCounts(
      allProjects,
      (p) => difficultyToRarity(p.difficulty),
      (p) => p.status === 'completed',
    ),
    [allProjects],
  );

  if (loading) return <Loader />;

  // A dropped fetch used to fall straight through to "No projects yet",
  // which reads as "my projects are gone" rather than "the network blinked"
  // — and an installed PWA has no reload button to escape it with.
  if (error) {
    return (
      <div className="space-y-3">
        <ErrorAlert message={error} />
        <Button variant="primary" onClick={reload}>
          Try again
        </Button>
      </div>
    );
  }

  const hasFilters = !!(statusFilter || typeFilter || childFilter || search);

  const renderProjectCard = (p) => (
    <motion.div
      key={p.id}
      variants={staggerItem}
      whileHover={{ y: -3 }}
      className="min-w-0"
    >
      <ParchmentCard className="h-full min-w-0">
        <motion.button
          type="button"
          className="block w-full min-h-11 text-left cursor-pointer rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-sheikah-teal"
          onClick={() => navigate(`/quests/ventures/${p.id}`)}
          aria-label={`Open ${p.title}`}
        >
          {p.cover_photo && (
            <img
              src={p.cover_photo}
              alt=""
              className="w-full h-32 object-cover rounded-lg mb-3 -mt-1 border border-ink-page-shadow"
            />
          )}
          <div className="flex items-start justify-between gap-2 mb-2">
            <h3 className="min-w-0 flex-1 break-words font-display text-lg leading-tight text-ink-primary">
              {p.title}
            </h3>
            <div className="shrink-0 flex items-center gap-1 flex-wrap justify-end">
              {p.payment_kind === 'bounty' && (
                <RuneBadge tone="royal" size="sm">optional project</RuneBadge>
              )}
              <StatusBadge status={p.status} />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 font-script text-caption text-ink-whisper mb-3">
            {p.category && (
              <span className="min-w-0 break-words flex items-center gap-1">
                {p.category.icon} {p.category.name}
              </span>
            )}
            <StarRating value={p.difficulty} />
          </div>
          {p.milestones_total > 0 && (
            <div className="mb-2">
              <div className="flex justify-between font-rune text-tiny text-ink-whisper mb-1">
                <span>MILESTONES</span>
                <span>{p.milestones_completed}/{p.milestones_total}</span>
              </div>
              <div className="h-1.5 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal"
                  style={{ width: `${(p.milestones_completed / p.milestones_total) * 100}%` }}
                />
              </div>
            </div>
          )}
          {p.assigned_to && (
            <div className="font-script text-caption text-ink-secondary break-words">
              assigned to {p.assigned_to.display_name || p.assigned_to.username}
            </div>
          )}
          {!p.assigned_to && p.payment_kind === 'bounty' && (
            <div className="font-script text-caption text-royal">available to claim</div>
          )}
        </motion.button>
        {p.due_date && (
          <div className="flex flex-wrap items-center gap-2 mt-3">
            <span className="font-script text-caption text-ink-whisper">
              due {formatDate(p.due_date)}
            </span>
            <AddToCalendar event={{
              id: `project:${p.id}`,
              title: `Project due: ${p.title}`,
              start: p.due_date,
              description: 'Project due date.',
              path: `/quests/ventures/${p.id}`,
            }} />
          </div>
        )}
      </ParchmentCard>
    </motion.div>
  );

  return (
    <div className="space-y-6">
      <QuestFolio
        letter="P"
        title="Projects"
        kicker="Plan and complete your projects"
        stats={[
          { value: inProgressCount, label: 'in progress' },
          { value: completedCount, label: 'done' },
        ]}
        progressPct={progressPct}
        progressLabel={
          totalCount > 0
            ? `${completedCount} of ${totalCount} projects complete`
            : '0 projects completed'
        }
        rarityCounts={totalCount > 0 ? rarityCounts : undefined}
      >
        {/* New-venture action — top of the recto so it stays reachable
            regardless of folio state. */}
        {isParent && (
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={() => navigate('/quests/ventures/new')}
              className="flex items-center gap-2"
            >
              <Plus size={16} /> New project
            </Button>
          </div>
        )}

        {/* Filters */}
        {allProjects.length > 0 && (
          <CatalogSearch
            value={search}
            onChange={setSearch}
            placeholder="Search projects…"
            ariaLabel="Filter projects"
          />
        )}
        <div className="flex flex-wrap gap-2 items-center">
          <SelectField
            variant="filter"
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </SelectField>
          <SelectField
            variant="filter"
            aria-label="Filter by type"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            {TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </SelectField>
          {isParent && children.length > 0 && (
            <SelectField
              variant="filter"
              aria-label="Filter by child"
              value={childFilter}
              onChange={(e) => setChildFilter(e.target.value)}
            >
              <option value="">All children</option>
              <option value="unassigned">Unassigned</option>
              {children.map((c) => (
                <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
              ))}
            </SelectField>
          )}
          {hasFilters && (
            <>
              <span className="font-script text-caption text-sheikah-teal-deep tabular-nums">
                {projects.length} {projects.length === 1 ? 'match' : 'matches'}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={clearAllFilters}
                className="font-script text-caption text-ink-whisper hover:text-ink-primary"
              >
                clear filters
              </Button>
            </>
          )}
        </div>

        {projects.length === 0 ? (
          <EmptyState icon={<InkwellIcon size={32} />}>
            {allProjects.length === 0
              ? `No projects yet. ${isParent ? 'Add one to get started.' : 'Ask a parent to add one.'}`
              : 'No projects match your filters.'}
          </EmptyState>
        ) : (
          STATUS_RUBRICS.map((rubric, idx) => {
            const rows = groupedProjects.get(rubric.key) ?? [];
            if (rows.length === 0) return null;
            return (
              <section key={rubric.key}>
                <ChapterRubric index={idx} name={rubric.label} />
                <motion.div
                  variants={staggerChildren}
                  initial="initial"
                  animate="animate"
                  className="grid md:grid-cols-2 xl:grid-cols-3 gap-4"
                >
                  {rows.map(renderProjectCard)}
                </motion.div>
              </section>
            );
          })
        )}
      </QuestFolio>

      {/* AI Suggestions — outside the folio so they read as a separate
          aside, the way "Suggested projects" already does. */}
      {suggestions?.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={18} className="text-gold-leaf" />
            <div>
              <div className="font-script text-xs text-ink-whisper uppercase tracking-wider">
                Suggested projects
              </div>
              <h2 className="font-display text-xl text-ink-primary leading-tight">
                Projects to try next
              </h2>
            </div>
          </div>
          <div className="grid md:grid-cols-3 gap-3">
            {suggestions.map((s, i) => (
              <motion.div
                key={s.title}
                initial={{ y: 10, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: i * 0.08 }}
              >
                <ParchmentCard className="border-sheikah-teal/40">
                  <div className="font-display text-base text-ink-primary mb-1 leading-tight">
                    {s.title}
                  </div>
                  <div className="font-body text-xs text-ink-secondary mb-2">
                    {s.description}
                  </div>
                  <div className="flex items-center gap-2 font-script text-xs text-ink-whisper">
                    {s.category && (
                      <span className="bg-ink-page-shadow/40 px-1.5 py-0.5 rounded font-body">
                        {s.category}
                      </span>
                    )}
                    <StarRating value={s.difficulty || 1} />
                    {s.estimated_hours && <span>{s.estimated_hours}h est.</span>}
                  </div>
                  {s.why && (
                    <div className="font-script text-xs text-sheikah-teal-deep mt-2 italic">
                      {s.why}
                    </div>
                  )}
                </ParchmentCard>
              </motion.div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
