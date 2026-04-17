import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plus, Sparkles } from 'lucide-react';
import { getProjects, getProjectSuggestions, getChildren } from '../api';
import { useApi } from '../hooks/useApi';
import StarRating from '../components/StarRating';
import EmptyState from '../components/EmptyState';
import Loader from '../components/Loader';
import StatusBadge from '../components/StatusBadge';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import { InkwellIcon } from '../components/icons/JournalIcons';
import { useRole } from '../hooks/useRole';
import { buttonPrimary, inputClass } from '../constants/styles';
import { normalizeList } from '../utils/api';
import { staggerChildren, staggerItem } from '../motion/variants';

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
  { value: 'bounty', label: 'Bounty' },
];

// intentional: compact filter selects need py-1.5 / text-sm / w-auto sizing that
// SelectField doesn't expose. Keep using raw inputClass + dimensional overrides.
const filterSelect = `${inputClass} py-1.5 text-sm w-auto min-w-[9rem]`;

export default function Projects() {
  const { isParent } = useRole();
  const { data, loading } = useApi(getProjects);
  const { data: suggestions } = useApi(getProjectSuggestions);
  const { data: childrenData } = useApi(getChildren);
  const navigate = useNavigate();

  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [childFilter, setChildFilter] = useState('');

  if (loading) return <Loader />;
  const allProjects = normalizeList(data);
  const children = normalizeList(childrenData);

  const projects = allProjects.filter((p) => {
    if (statusFilter && p.status !== statusFilter) return false;
    if (typeFilter && p.payment_kind !== typeFilter) return false;
    if (childFilter) {
      if (childFilter === 'unassigned') return !p.assigned_to;
      if (p.assigned_to?.id !== parseInt(childFilter)) return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            ventures · the big adventures
          </div>
          <h2 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight">
            All ventures
          </h2>
        </div>
        {isParent && (
          <button
            type="button"
            onClick={() => navigate('/quests/ventures/new')}
            className={`flex items-center gap-2 px-4 py-2 text-sm ${buttonPrimary}`}
          >
            <Plus size={16} /> New venture
          </button>
        )}
      </header>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className={filterSelect}
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className={filterSelect}
        >
          {TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {isParent && children.length > 0 && (
          <select
            value={childFilter}
            onChange={(e) => setChildFilter(e.target.value)}
            className={filterSelect}
          >
            <option value="">All children</option>
            <option value="unassigned">Unassigned</option>
            {children.map((c) => (
              <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
            ))}
          </select>
        )}
        {(statusFilter || typeFilter || childFilter) && (
          <button
            type="button"
            onClick={() => { setStatusFilter(''); setTypeFilter(''); setChildFilter(''); }}
            className="font-script text-xs text-ink-whisper hover:text-ink-primary px-2 py-1.5 transition-colors"
          >
            clear filters
          </button>
        )}
      </div>

      {projects.length === 0 ? (
        <EmptyState icon={<InkwellIcon size={32} />}>
          {allProjects.length === 0
            ? `No ventures yet. ${isParent ? 'Inscribe one to get started!' : 'Ask a parent to inscribe one!'}`
            : 'No ventures match your filters.'}
        </EmptyState>
      ) : (
        <motion.div
          variants={staggerChildren}
          initial="initial"
          animate="animate"
          className="grid md:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {projects.map((p) => (
            <motion.div
              key={p.id}
              variants={staggerItem}
              whileHover={{ y: -3 }}
              className="cursor-pointer"
              onClick={() => navigate(`/quests/ventures/${p.id}`)}
            >
              <ParchmentCard className="h-full">
                {p.cover_photo && (
                  <img
                    src={p.cover_photo}
                    alt=""
                    className="w-full h-32 object-cover rounded-lg mb-3 -mt-1 border border-ink-page-shadow"
                  />
                )}
                <div className="flex items-start justify-between gap-2 mb-2">
                  <h3 className="font-display text-lg leading-tight text-ink-primary">
                    {p.title}
                  </h3>
                  <div className="flex items-center gap-1 flex-wrap justify-end">
                    {p.payment_kind === 'bounty' && (
                      <RuneBadge tone="royal" size="sm">bounty</RuneBadge>
                    )}
                    <StatusBadge status={p.status} />
                  </div>
                </div>
                <div className="flex items-center gap-3 font-script text-xs text-ink-whisper mb-3">
                  {p.category && (
                    <span className="flex items-center gap-1">
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
                  <div className="font-script text-xs text-ink-secondary">
                    assigned to {p.assigned_to.display_name || p.assigned_to.username}
                  </div>
                )}
                {!p.assigned_to && p.payment_kind === 'bounty' && (
                  <div className="font-script text-xs text-royal">open bounty</div>
                )}
              </ParchmentCard>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* AI Suggestions */}
      {suggestions?.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={18} className="text-gold-leaf" />
            <div>
              <div className="font-script text-xs text-ink-whisper uppercase tracking-wider">
                whispered suggestions
              </div>
              <h2 className="font-display text-xl text-ink-primary leading-tight">
                Next ventures to consider
              </h2>
            </div>
          </div>
          <div className="grid md:grid-cols-3 gap-3">
            {suggestions.map((s, i) => (
              <motion.div
                key={i}
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
