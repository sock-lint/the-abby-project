import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Play, Square, Clock, Ban } from 'lucide-react';
import { getClockStatus, clockIn, clockOut, getProjects, getTimeEntries, voidTimeEntry } from '../api';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import Card from '../components/Card';
import ConfirmDialog from '../components/ConfirmDialog';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { formatDate, formatDuration } from '../utils/format';
import { normalizeList } from '../utils/api';

export default function ClockPage() {
  const { isParent } = useRole();
  const { data: status, reload: reloadStatus } = useApi(getClockStatus);
  const { data: projectsData } = useApi(getProjects);
  const { data: entriesData, reload: reloadEntries } = useApi(getTimeEntries);
  const [selectedProject, setSelectedProject] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const [voidEntryId, setVoidEntryId] = useState(null);

  const projects = normalizeList(projectsData);
  const entries = normalizeList(entriesData);
  const isClocked = status && status.status === 'active';

  useEffect(() => {
    if (!isClocked || !status?.clock_in) return;
    const start = new Date(status.clock_in).getTime();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [isClocked, status?.clock_in]);

  const formatTime = (secs) => {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const handleClockIn = async () => {
    setError('');
    if (!selectedProject) { setError('Select a project'); return; }
    try {
      await clockIn(parseInt(selectedProject));
      reloadStatus();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleClockOut = async () => {
    setError('');
    try {
      await clockOut(notes);
      setNotes('');
      reloadStatus();
      reloadEntries();
    } catch (err) {
      setError(err.message);
    }
  };

  const confirmVoid = async () => {
    const entryId = voidEntryId;
    setVoidEntryId(null);
    try {
      await voidTimeEntry(entryId);
      reloadEntries();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="font-heading text-2xl font-bold text-center">Clock</h1>

      {/* Timer Display */}
      <motion.div layout>
        <Card className={`text-center py-8 ${isClocked ? 'border-amber-primary/50' : ''}`}>
          <AnimatePresence mode="wait">
            {isClocked ? (
              <motion.div key="active" initial={{ scale: 0.8 }} animate={{ scale: 1 }}>
                <div className="text-sm text-amber-highlight mb-2 font-medium">
                  Working on: {status.project_title}
                </div>
                <div className="font-heading text-5xl md:text-6xl font-bold text-amber-glow mb-6 tabular-nums">
                  {formatTime(elapsed)}
                </div>
                <div className="mb-4">
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="What did you work on?"
                    inputMode="text"
                    className="w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-base text-forge-text resize-none h-20 focus:outline-none focus:border-amber-primary"
                  />
                </div>
                <motion.button
                  whileTap={{ scale: 0.95 }}
                  onClick={handleClockOut}
                  className="w-32 h-32 mx-auto rounded-full bg-red-600 hover:bg-red-500 flex items-center justify-center text-white shadow-lg shadow-red-600/30 transition-colors"
                >
                  <Square size={40} />
                </motion.button>
                <div className="text-sm text-forge-text-dim mt-3">Tap to Clock Out</div>
              </motion.div>
            ) : (
              <motion.div key="idle" initial={{ scale: 0.8 }} animate={{ scale: 1 }}>
                <Clock className="text-forge-text-dim mx-auto mb-3" size={32} />
                <div className="font-heading text-5xl md:text-6xl font-bold text-forge-text-dim mb-6">
                  00:00:00
                </div>
                <div className="mb-4">
                  <select
                    value={selectedProject}
                    onChange={(e) => setSelectedProject(e.target.value)}
                    className="w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-base text-forge-text focus:outline-none focus:border-amber-primary"
                  >
                    <option value="">Select a project...</option>
                    {projects.filter(p => ['active', 'in_progress'].includes(p.status)).map((p) => (
                      <option key={p.id} value={p.id}>{p.title}</option>
                    ))}
                  </select>
                </div>
                <motion.button
                  whileTap={{ scale: 0.95 }}
                  onClick={handleClockIn}
                  className="w-32 h-32 mx-auto rounded-full bg-green-600 hover:bg-green-500 flex items-center justify-center text-white shadow-lg shadow-green-600/30 transition-colors"
                >
                  <Play size={40} className="ml-1" />
                </motion.button>
                <div className="text-sm text-forge-text-dim mt-3">Tap to Clock In</div>
              </motion.div>
            )}
          </AnimatePresence>
        </Card>
      </motion.div>

      <ErrorAlert message={error} />

      {/* Recent Entries */}
      {entries.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3">Recent Entries</h2>
          <div className="space-y-2">
            {entries.slice(0, 10).map((e) => (
              <Card key={e.id} className={`flex items-center justify-between text-sm ${e.status === 'voided' ? 'opacity-50' : ''}`}>
                <div>
                  <div className={`font-medium ${e.status === 'voided' ? 'line-through' : ''}`}>{e.project_title}</div>
                  <div className="text-xs text-forge-text-dim">
                    {formatDate(e.clock_in)} {e.notes && `— ${e.notes}`}
                    {e.status === 'voided' && <span className="text-red-400 ml-1">(voided)</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="font-heading font-bold text-forge-text-dim">
                    {e.duration_minutes ? formatDuration(e.duration_minutes) : '...'}
                  </div>
                  {isParent && e.status !== 'voided' && e.status !== 'active' && (
                    <button
                      onClick={() => setVoidEntryId(e.id)}
                      title="Void entry"
                      className="text-forge-text-dim hover:text-red-400 p-1 transition-colors"
                    >
                      <Ban size={14} />
                    </button>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {voidEntryId && (
        <ConfirmDialog
          title="Void this time entry?"
          message="This cannot be undone."
          confirmLabel="Void"
          onConfirm={confirmVoid}
          onCancel={() => setVoidEntryId(null)}
        />
      )}
    </div>
  );
}
