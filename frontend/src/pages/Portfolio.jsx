import { useState, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Image, Download, Plus, Camera, BookOpen,
  X, ChevronLeft, ChevronRight, Trash2, Clapperboard,
  Palette, Music, Send,
} from 'lucide-react';
import SubjectBadge from '../components/SubjectBadge';
import {
  getPortfolio, getProjects, uploadPhoto,
  deletePhoto, deleteHomeworkProof,
  deleteCreation, submitCreation,
} from '../api';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import BottomSheet from '../components/BottomSheet';
import EmptyState from '../components/EmptyState';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import Button from '../components/Button';
import IconButton from '../components/IconButton';
import ConfirmDialog from '../components/ConfirmDialog';
import { TextField, SelectField } from '../components/form';
import { downscaleImage } from '../utils/image';
import { formatMonth } from '../utils/format';
import { normalizeList } from '../utils/api';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'projects', label: 'Projects' },
  { key: 'homework', label: 'Homework' },
  { key: 'creations', label: 'Creations' },
  { key: 'timelapses', label: 'Timelapses' },
];

export default function Portfolio() {
  const { user, isParent } = useRole();
  const { data, loading, reload } = useApi(getPortfolio);
  const { data: projectsData } = useApi(getProjects);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [filter, setFilter] = useState('all');
  const [sortMode, setSortMode] = useState('project');
  const [viewer, setViewer] = useState({ open: false, index: 0, items: [] });
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleteError, setDeleteError] = useState('');
  const [deleting, setDeleting] = useState(false);

  const allItems = useMemo(() => {
    if (!data) return [];
    const out = [];
    (data.projects || []).forEach((g) => {
      (g.photos || []).forEach((p) => {
        out.push({
          id: `proj-${p.id}`,
          kind: 'project',
          deleteId: p.id,
          ownerId: p.user,
          image: p.image,
          caption: p.caption,
          groupKey: g.project_id,
          groupLabel: g.project_title,
          date: p.uploaded_at,
          isTimelapse: !!p.is_timelapse,
        });
      });
    });
    (data.homework || []).forEach((g) => {
      (g.items || []).forEach((it) => {
        out.push({
          id: `hw-${it.id}`,
          kind: 'homework',
          deleteId: it.id,
          ownerId: it.user_id,
          image: it.image,
          caption: it.caption,
          groupKey: g.subject,
          groupLabel: it.assignment_title,
          date: it.submitted_at,
          isTimelapse: false,
        });
      });
    });
    (data.creations || []).forEach((c) => {
      out.push({
        id: `cr-${c.id}`,
        kind: 'creation',
        rawId: c.id,
        deleteId: c.id,
        ownerId: c.user_id,
        image: c.image,
        audio: c.audio,
        caption: c.caption,
        groupKey: c.primary_skill_category || 'Creations',
        groupLabel: c.primary_skill_name || 'Creation',
        date: c.created_at,
        isTimelapse: false,
        creationStatus: c.status,
        bonusXp: c.bonus_xp_awarded,
      });
    });
    return out;
  }, [data]);

  const counts = useMemo(() => ({
    all: allItems.length,
    projects: allItems.filter((i) => i.kind === 'project').length,
    homework: allItems.filter((i) => i.kind === 'homework').length,
    creations: allItems.filter((i) => i.kind === 'creation').length,
    timelapses: allItems.filter((i) => i.isTimelapse).length,
  }), [allItems]);

  const filteredItems = useMemo(() => {
    if (filter === 'all') return allItems;
    if (filter === 'projects') return allItems.filter((i) => i.kind === 'project');
    if (filter === 'homework') return allItems.filter((i) => i.kind === 'homework');
    if (filter === 'creations') return allItems.filter((i) => i.kind === 'creation');
    if (filter === 'timelapses') return allItems.filter((i) => i.isTimelapse);
    return allItems;
  }, [allItems, filter]);

  const byGroup = useMemo(() => {
    const map = new Map();
    filteredItems.forEach((it) => {
      const key = `${it.kind}:${it.groupKey}`;
      if (!map.has(key)) {
        map.set(key, {
          key,
          kind: it.kind,
          label: it.kind === 'project' ? it.groupLabel : it.groupKey,
          items: [],
        });
      }
      map.get(key).items.push(it);
    });
    return [...map.values()];
  }, [filteredItems]);

  const byDate = useMemo(() => {
    const sorted = [...filteredItems].sort(
      (a, b) => new Date(b.date) - new Date(a.date),
    );
    const map = new Map();
    sorted.forEach((it) => {
      const d = new Date(it.date);
      const monthKey = `${d.getFullYear()}-${String(d.getMonth()).padStart(2, '0')}`;
      const monthLabel = formatMonth(it.date);
      if (!map.has(monthKey)) map.set(monthKey, { key: monthKey, label: monthLabel, items: [] });
      map.get(monthKey).items.push(it);
    });
    return [...map.values()];
  }, [filteredItems]);

  const orderedItems = useMemo(() => {
    if (sortMode === 'date') return byDate.flatMap((m) => m.items);
    return byGroup.flatMap((g) => g.items);
  }, [sortMode, byDate, byGroup]);

  if (loading) return <Loader />;

  const openViewer = (item) => {
    const idx = orderedItems.findIndex((i) => i.id === item.id);
    setViewer({ open: true, index: Math.max(0, idx), items: orderedItems });
  };
  const closeViewer = () => setViewer((v) => ({ ...v, open: false }));
  const viewerPrev = () => setViewer((v) => ({ ...v, index: Math.max(0, v.index - 1) }));
  const viewerNext = () =>
    setViewer((v) => ({ ...v, index: Math.min(v.items.length - 1, v.index + 1) }));

  const canDelete = (item) => isParent || item.ownerId === user?.id;

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    const fn =
      target.kind === 'creation' ? deleteCreation
        : target.kind === 'project' ? deletePhoto
        : deleteHomeworkProof;
    setDeleting(true);
    setDeleteError('');
    try {
      await fn(target.deleteId);
      setPendingDelete(null);
      await reload();
    } catch (err) {
      // Surface the failure so users (and us) can see why nothing was removed.
      const msg = err?.message || String(err) || 'Delete failed';
      setDeleteError(`Couldn't remove that page: ${msg}`);
      console.error('[Sketchbook] delete failed', { target, err });
    } finally {
      setDeleting(false);
    }
  };

  const handleSubmitForBonus = async (item) => {
    try {
      await submitCreation(item.rawId);
      await reload();
    } catch (err) {
      const msg = err?.message || String(err) || 'Submit failed';
      setDeleteError(`Couldn't submit that creation: ${msg}`);
    }
  };

  const projects = normalizeList(projectsData);
  const hasContent = allItems.length > 0;

  return (
    <div className="space-y-6">
      {deleteError && <ErrorAlert message={deleteError} />}
      <header className="flex items-start justify-between gap-2 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            the sketchbook · pressed between pages
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Sketchbook
          </h1>
          <div className="font-script text-sm text-ink-whisper mt-1 max-w-xl">
            every photo from your ventures, study proofs, and creations · tap a tile to leaf through
          </div>
        </div>
        <div className="flex items-center gap-2">
          {hasContent && (
            <a
              href="/api/export/portfolio/"
              className="flex items-center gap-1.5 font-script text-sm text-sheikah-teal-deep hover:text-sheikah-teal transition-colors px-2 min-h-10"
            >
              <Download size={16} /> <span className="hidden sm:inline">download all</span>
            </a>
          )}
          <Button
            size="sm"
            onClick={() => setUploadOpen(true)}
            className="flex items-center gap-1.5 min-h-10"
          >
            <Plus size={16} /> Affix photo
          </Button>
        </div>
      </header>

      {hasContent && (
        <div className="space-y-2">
          <div
            role="tablist"
            aria-label="Filter Sketchbook"
            className="flex flex-wrap gap-1 bg-ink-page-aged rounded-lg p-1 border border-ink-page-shadow"
          >
            {FILTERS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={filter === key}
                onClick={() => setFilter(key)}
                disabled={counts[key] === 0}
                className={`flex-1 min-w-[5rem] px-3 py-1.5 rounded-md font-display text-sm transition-colors disabled:opacity-40 ${
                  filter === key
                    ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
                    : 'text-ink-secondary hover:text-ink-primary'
                }`}
              >
                {label}{' '}
                <span className="opacity-70">({counts[key]})</span>
              </button>
            ))}
          </div>
          <div
            className="flex gap-2 text-xs font-script text-ink-whisper items-center justify-end"
            role="group"
            aria-label="Sort"
          >
            <span aria-hidden="true">Arrange:</span>
            <button
              type="button"
              onClick={() => setSortMode('project')}
              aria-pressed={sortMode === 'project'}
              className={
                sortMode === 'project'
                  ? 'text-sheikah-teal-deep underline'
                  : 'hover:text-ink-primary'
              }
            >
              By project
            </button>
            <span aria-hidden="true">·</span>
            <button
              type="button"
              onClick={() => setSortMode('date')}
              aria-pressed={sortMode === 'date'}
              className={
                sortMode === 'date'
                  ? 'text-sheikah-teal-deep underline'
                  : 'hover:text-ink-primary'
              }
            >
              By date
            </button>
          </div>
          {filter === 'creations' && (
            <p className="font-script text-tiny text-ink-whisper text-center">
              creations log what you made — first two of the day earn XP; submit for a bonus seal
            </p>
          )}
        </div>
      )}

      {!hasContent ? (
        <EmptyState icon={<Image size={32} />}>
          No pages yet — affix your first progress photo and it'll appear here.
        </EmptyState>
      ) : filteredItems.length === 0 ? (
        <EmptyState icon={<Image size={32} />}>
          Nothing filed under “{filter}” yet.
        </EmptyState>
      ) : sortMode === 'project' ? (
        byGroup.map((group) => (
          <section key={group.key}>
            <h2 className="font-display text-xl text-ink-primary leading-tight mb-3 flex items-center gap-2">
              {group.kind === 'homework' && (
                <BookOpen size={18} className="text-sheikah-teal-deep" />
              )}
              {group.kind === 'creation' && (
                <Palette size={18} className="text-gold-leaf" />
              )}
              {group.kind === 'homework'
                ? <SubjectBadge subject={group.label} />
                : group.label}
            </h2>
            <PhotoGrid
              items={group.items}
              onOpen={openViewer}
              onRequestDelete={setPendingDelete}
              onSubmitForBonus={handleSubmitForBonus}
              canDelete={canDelete}
            />
          </section>
        ))
      ) : (
        byDate.map((month) => (
          <section key={month.key}>
            <h2 className="font-display text-xl text-ink-primary leading-tight mb-3">
              {month.label}
            </h2>
            <PhotoGrid
              items={month.items}
              onOpen={openViewer}
              onRequestDelete={setPendingDelete}
              onSubmitForBonus={handleSubmitForBonus}
              canDelete={canDelete}
              showMeta
            />
          </section>
        ))
      )}

      <AnimatePresence>
        {uploadOpen && (
          <UploadSheet
            projects={projects}
            onClose={() => setUploadOpen(false)}
            onUploaded={() => {
              reload();
              setUploadOpen(false);
            }}
          />
        )}
      </AnimatePresence>

      {viewer.open && (
        <Lightbox
          viewer={viewer}
          onClose={closeViewer}
          onPrev={viewerPrev}
          onNext={viewerNext}
        />
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Remove from Sketchbook?"
          message="This pulls the page out for good — it can't be restored."
          confirmLabel="Remove"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}

function PhotoGrid({ items, onOpen, onRequestDelete, onSubmitForBonus, canDelete, showMeta }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {items.map((item, i) => (
        <motion.div
          key={item.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: Math.min(i * 0.04, 0.4) }}
          className="relative"
        >
          <button
            type="button"
            onClick={() => onOpen(item)}
            aria-label={`View ${item.caption || item.groupLabel}`}
            className="block relative aspect-square w-full rounded-xl overflow-hidden bg-ink-page-aged border border-ink-page-shadow shadow-sm hover:shadow-md transition-shadow focus:outline-none focus:ring-2 focus:ring-sheikah-teal"
          >
            <img
              src={item.image}
              alt={item.caption || item.groupLabel}
              className="w-full h-full object-cover"
            />
            {item.isTimelapse && (
              <div
                aria-label="Timelapse"
                className="absolute top-1.5 left-1.5 rounded-full bg-ink-primary/70 text-ink-page-rune-glow p-1"
              >
                <Clapperboard size={12} />
              </div>
            )}
            {item.kind === 'creation' && (
              <div
                aria-label="Creation"
                className="absolute top-1.5 left-1.5 rounded-full bg-gold-leaf/85 text-ink-primary p-1"
              >
                <Palette size={12} />
              </div>
            )}
            {item.kind === 'creation' && item.audio && (
              <div
                aria-label="Has audio"
                className="absolute top-1.5 left-9 rounded-full bg-sheikah-teal-deep/85 text-ink-page-rune-glow p-1"
                title="This creation has an audio attachment"
              >
                <Music size={12} />
              </div>
            )}
            {item.kind === 'creation' && item.creationStatus === 'approved' && (
              <div
                aria-label={`Parent bonus: +${item.bonusXp} XP`}
                className="absolute bottom-1.5 left-1.5 rounded-full bg-royal text-ink-page-rune-glow px-1.5 py-0.5 text-micro font-display"
                title={`Parent bonus granted: +${item.bonusXp} XP`}
              >
                🏅 +{item.bonusXp}
              </div>
            )}
            {item.kind === 'creation' && item.creationStatus === 'pending' && (
              <div
                aria-label="Bonus pending review"
                className="absolute bottom-1.5 left-1.5 rounded-full bg-ink-primary/70 text-ink-page-rune-glow px-2 py-0.5 text-micro font-script"
              >
                pending
              </div>
            )}
            {(item.caption || showMeta || item.kind === 'homework') && (
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-ink-primary/85 to-transparent p-2 text-left">
                <div className="font-script text-xs text-ink-page-rune-glow truncate">
                  {item.caption || item.groupLabel}
                </div>
                {showMeta && item.caption && (
                  <div className="font-script text-micro text-ink-page-rune-glow/80 truncate">
                    {item.groupLabel}
                  </div>
                )}
              </div>
            )}
          </button>
          {item.kind === 'creation' && item.creationStatus === 'logged' && onSubmitForBonus && (
            <IconButton
              aria-label={`Submit ${item.caption || item.groupLabel} for parent bonus`}
              variant="ghost"
              size="sm"
              className="absolute bottom-1.5 right-1.5 !bg-royal/85 hover:!bg-royal !text-ink-page-rune-glow"
              onClick={(e) => {
                e.stopPropagation();
                onSubmitForBonus(item);
              }}
              title="Submit for parent bonus review"
            >
              <Send size={14} />
            </IconButton>
          )}
          {canDelete(item) && (
            <IconButton
              aria-label={`Delete ${item.caption || item.groupLabel}`}
              variant="ghost"
              size="sm"
              className="absolute top-1.5 right-1.5 !bg-ink-primary/75 hover:!bg-ink-primary !text-ink-page-rune-glow"
              onClick={(e) => {
                e.stopPropagation();
                onRequestDelete(item);
              }}
            >
              <Trash2 size={14} />
            </IconButton>
          )}
        </motion.div>
      ))}
    </div>
  );
}

function Lightbox({ viewer, onClose, onPrev, onNext }) {
  const current = viewer.items[viewer.index];
  if (!current) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Photo viewer"
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center"
      onClick={onClose}
    >
      <IconButton
        onClick={(e) => { e.stopPropagation(); onClose(); }}
        variant="ghost"
        aria-label="Close photo viewer"
        className="absolute top-4 right-4 text-white/70 hover:text-white"
      >
        <X size={24} />
      </IconButton>
      {viewer.index > 0 && (
        <IconButton
          onClick={(e) => { e.stopPropagation(); onPrev(); }}
          variant="ghost"
          aria-label="Previous photo"
          className="absolute left-4 text-white/70 hover:text-white"
        >
          <ChevronLeft size={32} />
        </IconButton>
      )}
      {viewer.index < viewer.items.length - 1 && (
        <IconButton
          onClick={(e) => { e.stopPropagation(); onNext(); }}
          variant="ghost"
          aria-label="Next photo"
          className="absolute right-4 text-white/70 hover:text-white"
        >
          <ChevronRight size={32} />
        </IconButton>
      )}
      <img
        src={current.image}
        alt={current.caption || current.groupLabel}
        className="max-h-[75vh] max-w-[90vw] object-contain rounded-lg"
        onClick={(e) => e.stopPropagation()}
      />
      <div className="absolute bottom-6 text-center left-0 right-0 px-4 space-y-2">
        {current.kind === 'creation' && current.audio && (
          <audio
            controls
            src={current.audio}
            preload="metadata"
            className="mx-auto max-w-[90vw] w-80"
            onClick={(e) => e.stopPropagation()}
          >
            Your browser doesn&apos;t support inline audio.
          </audio>
        )}
        <div className="font-script text-white/90 text-sm">
          {current.caption || current.groupLabel}
        </div>
      </div>
    </div>
  );
}

function UploadSheet({ projects, onClose, onUploaded }) {
  const [projectId, setProjectId] = useState('');
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [caption, setCaption] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setError('');
  };

  const handleSubmit = async () => {
    if (!projectId) {
      setError('Pick a project first.');
      return;
    }
    if (!file) {
      setError('Pick a photo first.');
      return;
    }
    setError('');
    setUploading(true);
    try {
      const processed = await downscaleImage(file);
      await uploadPhoto(projectId, processed, caption);
      onUploaded();
    } catch (err) {
      setError(err.message || 'Upload failed');
      setUploading(false);
    }
  };

  return (
    <BottomSheet title="Upload Photo" onClose={onClose} disabled={uploading}>
      <ErrorAlert message={error} />

      <SelectField
        label="Project"
        value={projectId}
        onChange={(e) => setProjectId(e.target.value)}
        disabled={uploading}
      >
        <option value="">Select a project...</option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.title}
          </option>
        ))}
      </SelectField>

      <div>
        <label className="block text-sm text-ink-whisper mb-1">Photo</label>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleFile}
          className="hidden"
          disabled={uploading}
        />
        {preview ? (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="relative w-full aspect-video rounded-lg overflow-hidden bg-ink-page border border-ink-page-shadow"
          >
            <img src={preview} alt="" className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-black/0 hover:bg-black/40 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity text-white text-sm">
              Change photo
            </div>
          </button>
        ) : (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="w-full aspect-video rounded-lg border-2 border-dashed border-ink-page-shadow hover:border-sheikah-teal/60 transition-colors flex flex-col items-center justify-center gap-2 text-ink-whisper"
          >
            <Camera size={28} />
            <span className="text-sm">Take photo or choose from library</span>
          </button>
        )}
      </div>

      <TextField
        label="Caption (optional)"
        type="text"
        value={caption}
        onChange={(e) => setCaption(e.target.value)}
        placeholder="What are we looking at?"
        disabled={uploading}
        maxLength={255}
      />

      <Button
        onClick={handleSubmit}
        disabled={uploading || !file || !projectId}
        className="w-full"
      >
        {uploading ? 'Uploading…' : 'Upload Photo'}
      </Button>
    </BottomSheet>
  );
}
