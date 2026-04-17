import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Image, Download, Plus, Camera, BookOpen } from 'lucide-react';
import SubjectBadge from '../components/SubjectBadge';
import { getPortfolio, getProjects, uploadPhoto } from '../api';
import { useApi } from '../hooks/useApi';
import BottomSheet from '../components/BottomSheet';
import EmptyState from '../components/EmptyState';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { buttonPrimary } from '../constants/styles';
import { TextField, SelectField } from '../components/form';
import { downscaleImage } from '../utils/image';
import { normalizeList } from '../utils/api';

export default function Portfolio() {
  const { data, loading, reload } = useApi(getPortfolio);
  const { data: projectsData } = useApi(getProjects);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [filter, setFilter] = useState('all'); // all | projects | homework

  if (loading) return <Loader />;
  // Support both old (array) and new ({projects, homework}) response shapes.
  const isNewShape = data && !Array.isArray(data);
  const projectGroups = isNewShape ? (data.projects || []) : (data || []);
  const homeworkGroups = isNewShape ? (data.homework || []) : [];
  const groups = projectGroups;
  const projects = normalizeList(projectsData);
  const hasContent = projectGroups.length > 0 || homeworkGroups.length > 0;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-2 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            the sketchbook · pressed between pages
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Sketchbook
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {groups.length > 0 && (
            <a
              href="/api/export/portfolio/"
              className="flex items-center gap-1.5 font-script text-sm text-sheikah-teal-deep hover:text-sheikah-teal transition-colors px-2 min-h-10"
            >
              <Download size={16} /> <span className="hidden sm:inline">download all</span>
            </a>
          )}
          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            className={`flex items-center gap-1.5 text-sm px-3 min-h-10 ${buttonPrimary}`}
          >
            <Plus size={16} /> Affix photo
          </button>
        </div>
      </header>

      {/* Filter tabs — bookmark ribbons */}
      {hasContent && homeworkGroups.length > 0 && (
        <div className="flex gap-1 bg-ink-page-aged rounded-lg p-1 border border-ink-page-shadow">
          {['all', 'projects', 'homework'].map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`flex-1 px-3 py-1.5 rounded-md font-display text-sm transition-colors ${
                filter === f
                  ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
                  : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      )}

      {!hasContent ? (
        <EmptyState icon={<Image size={32} />}>
          No pages yet — affix your first progress photo and it'll appear here.
        </EmptyState>
      ) : (
        <>
          {/* Project photos */}
          {(filter === 'all' || filter === 'projects') && projectGroups.map((group) => (
            <div key={group.project_id}>
              <h2 className="font-display text-xl text-ink-primary leading-tight mb-3">
                {group.project_title}
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {group.photos.map((photo, i) => (
                  <motion.div
                    key={photo.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }}
                  >
                    <div className="relative aspect-square rounded-xl overflow-hidden bg-ink-page-aged border border-ink-page-shadow shadow-sm">
                      <img
                        src={photo.image}
                        alt={photo.caption}
                        className="w-full h-full object-cover"
                      />
                      {photo.caption && (
                        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-ink-primary/85 to-transparent p-2">
                          <div className="font-script text-xs text-ink-page-rune-glow truncate">
                            {photo.caption}
                          </div>
                        </div>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          ))}

          {/* Homework proofs */}
          {(filter === 'all' || filter === 'homework') && homeworkGroups.map((group) => (
            <div key={group.subject}>
              <h2 className="font-display text-xl text-ink-primary leading-tight mb-3 flex items-center gap-2">
                <BookOpen size={18} className="text-sheikah-teal-deep" />
                <SubjectBadge subject={group.subject} />
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {group.items.map((item, i) => (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }}
                  >
                    <div className="relative aspect-square rounded-xl overflow-hidden bg-ink-page-aged border border-ink-page-shadow shadow-sm">
                      <img
                        src={item.image}
                        alt={item.caption || item.assignment_title}
                        className="w-full h-full object-cover"
                      />
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-ink-primary/85 to-transparent p-2">
                        <div className="font-script text-xs text-ink-page-rune-glow truncate">
                          {item.assignment_title}
                        </div>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          ))}
        </>
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

      <button
        type="button"
        onClick={handleSubmit}
        disabled={uploading || !file || !projectId}
        className={`w-full py-3 disabled:cursor-not-allowed ${buttonPrimary}`}
      >
        {uploading ? 'Uploading…' : 'Upload Photo'}
      </button>
    </BottomSheet>
  );
}
