import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plus, Sparkles } from 'lucide-react';
import { getProjects, getProjectSuggestions } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import StatusBadge from '../components/StatusBadge';
import Loader from '../components/Loader';
import { normalizeList } from '../utils/api';

export default function Projects({ user }) {
  const { data, loading } = useApi(getProjects);
  const { data: suggestions } = useApi(getProjectSuggestions);
  const navigate = useNavigate();

  if (loading) return <Loader />;
  const projects = normalizeList(data);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold">Projects</h1>
        {user?.role === 'parent' && (
          <button
            onClick={() => navigate('/projects/new')}
            className="flex items-center gap-2 bg-amber-primary hover:bg-amber-highlight text-black font-semibold px-4 py-2 rounded-lg text-sm transition-colors"
          >
            <Plus size={16} /> New Project
          </button>
        )}
      </div>

      {projects.length === 0 ? (
        <Card className="text-center py-12 text-forge-text-dim">
          No projects yet. {user?.role === 'parent' ? 'Create one to get started!' : 'Ask a parent to create one!'}
        </Card>
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
                        🎯 Bounty
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
                  <span>{'★'.repeat(p.difficulty)}{'☆'.repeat(5 - p.difficulty)}</span>
                </div>
                {p.milestones_total > 0 && (
                  <div className="mb-2">
                    <div className="flex justify-between text-xs text-forge-text-dim mb-1">
                      <span>Progress</span>
                      <span>{p.milestones_completed}/{p.milestones_total}</span>
                    </div>
                    <div className="h-1.5 bg-forge-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-amber-primary rounded-full transition-all"
                        style={{ width: `${(p.milestones_completed / p.milestones_total) * 100}%` }}
                      />
                    </div>
                  </div>
                )}
                {p.assigned_to && (
                  <div className="text-xs text-forge-text-dim">
                    Assigned to {p.assigned_to.display_name || p.assigned_to.username}
                  </div>
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
                    <span>{'★'.repeat(s.difficulty || 1)}</span>
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
