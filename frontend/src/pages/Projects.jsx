import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plus, Sparkles } from 'lucide-react';
import { getProjects, getProjectSuggestions, getChildren } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import StarRating from '../components/StarRating';
import EmptyState from '../components/EmptyState';
import Loader from '../components/Loader';
import ProgressBar from '../components/ProgressBar';
import StatusBadge from '../components/StatusBadge';
import { useRole } from '../hooks/useRole';
import { buttonPrimary } from '../constants/styles';
import { normalizeList } from '../utils/api';

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'in_review', label: 'In Review' },
  { value: 'completed', label: 'Completed' },
];

const TYPE_OPTIONS = [
  { value: '', label: 'All Types' },
  { value: 'required', label: 'Required' },
  { value: 'bounty', label: 'Bounty' },
];

const filterSelect = 'bg-forge-bg border border-forge-border rounded-lg px-2 py-1.5 text-forge-text text-sm focus:outline-none focus:border-amber-primary';

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
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold">Projects</h1>
        {isParent && (
          <button
            onClick={() => navigate('/projects/new')}
            className={`flex items-center gap-2 px-4 py-2 text-sm ${buttonPrimary}`}
          >
            <Plus size={16} /> New Project
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={filterSelect}>
          {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className={filterSelect}>
          {TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {isParent && children.length > 0 && (
          <select value={childFilter} onChange={(e) => setChildFilter(e.target.value)} className={filterSelect}>
            <option value="">All Children</option>
            <option value="unassigned">Unassigned</option>
            {children.map((c) => (
              <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
            ))}
          </select>
        )}
        {(statusFilter || typeFilter || childFilter) && (
          <button
            onClick={() => { setStatusFilter(''); setTypeFilter(''); setChildFilter(''); }}
            className="text-xs text-forge-text-dim hover:text-forge-text px-2 py-1.5"
          >
            Clear filters
          </button>
        )}
      </div>

      {projects.length === 0 ? (
        <EmptyState>
          {allProjects.length === 0
            ? `No projects yet. ${isParent ? 'Create one to get started!' : 'Ask a parent to create one!'}`
            : 'No projects match your filters.'}
        </EmptyState>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p, i) => (
            <motion.div
              key={p.id}
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: i * 0.05 }}
              whileHover={{ y: -3 }}
              className="cursor-pointer"
              onClick={() => navigate(`/projects/${p.id}`)}
            >
              <Card className="h-full">
                {p.cover_photo && (
                  <img src={p.cover_photo} alt="" className="w-full h-32 object-cover rounded-lg mb-3 -mt-1" />
                )}
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-semibold text-forge-text">{p.title}</h3>
                  <div className="flex items-center gap-1">
                    {p.payment_kind === 'bounty' && (
                      <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-fuchsia-400/15 text-fuchsia-300 border border-fuchsia-400/30">
                        Bounty
                      </span>
                    )}
                    <StatusBadge status={p.status} />
                  </div>
                </div>
                <div className="flex items-center gap-3 text-xs text-forge-text-dim mb-3">
                  {p.category && (
                    <span className="flex items-center gap-1">
                      {p.category.icon} {p.category.name}
                    </span>
                  )}
                  <StarRating value={p.difficulty} />
                </div>
                {p.milestones_total > 0 && (
                  <div className="mb-2">
                    <div className="flex justify-between text-xs text-forge-text-dim mb-1">
                      <span>Progress</span>
                      <span>{p.milestones_completed}/{p.milestones_total}</span>
                    </div>
                    <ProgressBar value={p.milestones_completed} max={p.milestones_total} />
                  </div>
                )}
                {p.assigned_to && (
                  <div className="text-xs text-forge-text-dim">
                    Assigned to {p.assigned_to.display_name || p.assigned_to.username}
                  </div>
                )}
                {!p.assigned_to && p.payment_kind === 'bounty' && (
                  <div className="text-xs text-fuchsia-300">Open bounty</div>
                )}
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      {/* AI Suggestions */}
      {suggestions?.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
            <Sparkles size={18} className="text-amber-highlight" /> Suggested Next Projects
          </h2>
          <div className="grid md:grid-cols-3 gap-3">
            {suggestions.map((s, i) => (
              <motion.div
                key={i}
                initial={{ y: 10, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: i * 0.1 }}
              >
                <Card className="border-amber-primary/20">
                  <div className="font-semibold text-sm mb-1">{s.title}</div>
                  <div className="text-xs text-forge-text-dim mb-2">{s.description}</div>
                  <div className="flex items-center gap-2 text-xs text-forge-text-dim">
                    {s.category && <span className="bg-forge-muted px-1.5 py-0.5 rounded">{s.category}</span>}
                    <StarRating value={s.difficulty || 1} />
                    {s.estimated_hours && <span>{s.estimated_hours}h est.</span>}
                  </div>
                  {s.why && <div className="text-xs text-amber-highlight mt-2">{s.why}</div>}
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
