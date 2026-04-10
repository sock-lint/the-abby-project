import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Image, Download, Plus, X, Camera } from 'lucide-react';
import { getPortfolio, getProjects, uploadPhoto } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { downscaleImage } from '../utils/image';
import { normalizeList } from '../utils/api';

export default function Portfolio() {
  const { data, loading, reload } = useApi(getPortfolio);
  const { data: projectsData } = useApi(getProjects);
  const [uploadOpen, setUploadOpen] = useState(false);

  if (loading) return <Loader />;
  const groups = data || [];
  const projects = normalizeList(projectsData);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-2">
        <h1 className="font-heading text-2xl font-bold">Portfolio</h1>
        <div className="flex items-center gap-2">
          {groups.length > 0 && (
            <a
              href="/api/export/portfolio/"
              className="flex items-center gap-1.5 text-sm text-forge-text-dim hover:text-amber-highlight transition-colors px-2 min-h-10"
            >
              <Download size={16} /> <span className="hidden sm:inline">Download All</span>
            </a>
          )}
          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            className="flex items-center gap-1.5 text-sm bg-amber-primary hover:bg-amber-highlight text-black font-semibold px-3 min-h-10 rounded-lg transition-colors"
          >
            <Plus size={16} /> Upload
          </button>
        </div>
      </div>

      {groups.length === 0 ? (
        <Card className="text-center py-12 text-forge-text-dim">
          <Image className="mx-auto mb-3" size={32} />
          <div>No photos yet. Upload progress photos from your projects!</div>
        </Card>
      ) : (
        groups.map((group) => (
          <div key={group.project_id}>
            <h2 className="font-heading text-lg font-bold mb-3">{group.project_title}</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {group.photos.map((photo, i) => (
                <motion.div
                  key={photo.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                >
                  <div className="relative aspect-square rounded-xl overflow-hidden bg-forge-card border border-forge-border">
                    <img
                      src={photo.image}
                      alt={photo.caption}
                      className="w-full h-full object-cover"
                    />
                    {photo.caption && (
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
                        <div className="text-xs text-white truncate">{photo.caption}</div>
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
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

  const inputClass =
    'w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text text-base focus:outline-none focus:border-amber-primary';

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={uploading ? undefined : onClose}
        className="fixed inset-0 bg-black/60 z-40"
      />
      <motion.div
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        exit={{ y: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className="fixed bottom-0 left-0 right-0 bg-forge-card border-t border-forge-border rounded-t-2xl z-50 pb-[env(safe-area-inset-bottom)] max-h-[90vh] overflow-y-auto md:left-1/2 md:right-auto md:bottom-auto md:top-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-full md:max-w-md md:rounded-2xl md:border"
      >
        <div className="flex justify-center pt-2 md:hidden">
          <div className="w-10 h-1 rounded-full bg-forge-muted" />
        </div>
        <div className="flex items-center justify-between px-4 pt-3 pb-2">
          <h2 className="font-heading text-lg font-bold">Upload Photo</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={uploading}
            aria-label="Close"
            className="text-forge-text-dim hover:text-forge-text min-h-10 min-w-10 flex items-center justify-center rounded-lg"
          >
            <X size={20} />
          </button>
        </div>

        <div className="px-4 pb-4 space-y-3">
          <ErrorAlert message={error} />

          <div>
            <label className="block text-sm text-forge-text-dim mb-1">Project</label>
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className={inputClass}
              disabled={uploading}
            >
              <option value="">Select a project...</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-forge-text-dim mb-1">Photo</label>
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
                className="relative w-full aspect-video rounded-lg overflow-hidden bg-forge-bg border border-forge-border"
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
                className="w-full aspect-video rounded-lg border-2 border-dashed border-forge-border hover:border-amber-primary/60 transition-colors flex flex-col items-center justify-center gap-2 text-forge-text-dim"
              >
                <Camera size={28} />
                <span className="text-sm">Take photo or choose from library</span>
              </button>
            )}
          </div>

          <div>
            <label className="block text-sm text-forge-text-dim mb-1">Caption (optional)</label>
            <input
              type="text"
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              className={inputClass}
              placeholder="What are we looking at?"
              disabled={uploading}
              maxLength={255}
            />
          </div>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={uploading || !file || !projectId}
            className="w-full bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 disabled:cursor-not-allowed text-black font-semibold py-3 rounded-lg transition-colors"
          >
            {uploading ? 'Uploading…' : 'Upload Photo'}
          </button>
        </div>
      </motion.div>
    </>
  );
}
