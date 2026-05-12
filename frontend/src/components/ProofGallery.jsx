import { useEffect, useState } from 'react';
import { X, ChevronLeft, ChevronRight } from 'lucide-react';
import IconButton from './IconButton';

export default function ProofGallery({ proofs = [] }) {
  const [viewerIndex, setViewerIndex] = useState(null);

  useEffect(() => {
    if (viewerIndex === null) return undefined;
    const handler = (e) => {
      if (e.key === 'Escape') {
        setViewerIndex(null);
      } else if (e.key === 'ArrowLeft' && viewerIndex > 0) {
        setViewerIndex(viewerIndex - 1);
      } else if (e.key === 'ArrowRight' && viewerIndex < proofs.length - 1) {
        setViewerIndex(viewerIndex + 1);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [viewerIndex, proofs.length]);

  if (!proofs.length) return null;

  return (
    <>
      {/* Thumbnail strip — image-content button, not a primitive: wrapping
          an <img> in <Button> would inject the parchment styling under the
          photo. ``type="button"`` keeps it from submitting an enclosing form. */}
      <div className="flex gap-2 overflow-x-auto py-1">
        {proofs.map((proof, i) => (
          <button
            key={proof.id}
            type="button"
            onClick={() => setViewerIndex(i)}
            aria-label={`View ${proof.caption || `proof ${i + 1}`}`}
            className="shrink-0 w-16 h-16 rounded-lg overflow-hidden border border-white/10 hover:border-white/30 transition-colors"
          >
            <img src={proof.image} alt={proof.caption || `Proof ${i + 1}`} className="w-full h-full object-cover" />
          </button>
        ))}
      </div>

      {/* Full-screen viewer */}
      {viewerIndex !== null && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center" onClick={() => setViewerIndex(null)}>
          <IconButton
            onClick={() => setViewerIndex(null)}
            variant="ghost"
            aria-label="Close photo viewer"
            className="absolute top-4 right-4 text-white/70 hover:text-white"
          >
            <X size={24} />
          </IconButton>
          {viewerIndex > 0 && (
            <IconButton
              onClick={(e) => { e.stopPropagation(); setViewerIndex(viewerIndex - 1); }}
              variant="ghost"
              aria-label="Previous photo"
              className="absolute left-4 text-white/70 hover:text-white"
            >
              <ChevronLeft size={32} />
            </IconButton>
          )}
          {viewerIndex < proofs.length - 1 && (
            <IconButton
              onClick={(e) => { e.stopPropagation(); setViewerIndex(viewerIndex + 1); }}
              variant="ghost"
              aria-label="Next photo"
              className="absolute right-4 text-white/70 hover:text-white"
            >
              <ChevronRight size={32} />
            </IconButton>
          )}
          <img
            src={proofs[viewerIndex].image}
            alt={proofs[viewerIndex].caption || `Proof ${viewerIndex + 1}`}
            className="max-h-[85vh] max-w-[90vw] object-contain rounded-lg"
            onClick={(e) => e.stopPropagation()}
          />
          {proofs[viewerIndex].caption && (
            <p className="absolute bottom-6 text-white/80 text-sm">{proofs[viewerIndex].caption}</p>
          )}
        </div>
      )}
    </>
  );
}
