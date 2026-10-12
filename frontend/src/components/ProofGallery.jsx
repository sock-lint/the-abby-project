import { useCallback, useEffect, useRef, useState } from 'react';
import { X, ChevronLeft, ChevronRight } from 'lucide-react';
import IconButton from './IconButton';
import SwipeableImage from './SwipeableImage';
import useBackDismiss from '../hooks/useBackDismiss';
import useModalFocus from './modal/useModalFocus';

export default function ProofGallery({ proofs = [] }) {
  const [viewerIndex, setViewerIndex] = useState(null);

  const closeViewer = useCallback(() => setViewerIndex(null), []);

  // In the installed PWA back is the "close this photo" gesture; without the
  // history sentinel it navigated off the page holding the submission.
  // Shared with the Sketchbook lightbox (pages/Portfolio.jsx) so there is one
  // implementation of the trick.
  useBackDismiss(closeViewer, viewerIndex !== null);

  useEffect(() => {
    if (viewerIndex === null) return undefined;
    // Escape belongs to useModalFocus (ProofViewer), which owns it for every
    // modal layer; only the arrows are handled here.
    const handler = (e) => {
      if (e.key === 'ArrowLeft' && viewerIndex > 0) {
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
            onClick={(e) => {
              // Safari/iOS don't focus a button on tap; useModalFocus returns
              // focus to whatever was active when the viewer mounted.
              e.currentTarget.focus();
              setViewerIndex(i);
            }}
            aria-label={`View ${proof.caption || `proof ${i + 1}`}`}
            className="shrink-0 w-16 h-16 rounded-lg overflow-hidden border border-white/10 hover:border-white/30 transition-colors"
          >
            <img src={proof.image} alt={proof.caption || `Proof ${i + 1}`} className="w-full h-full object-cover" />
          </button>
        ))}
      </div>

      {viewerIndex !== null && (
        <ProofViewer
          proofs={proofs}
          index={viewerIndex}
          onIndexChange={setViewerIndex}
          onClose={closeViewer}
        />
      )}
    </>
  );
}

// Full-screen viewer. Mounted only while open so useModalFocus records the
// opening thumbnail as the element to restore focus to on close.
function ProofViewer({ proofs, index, onIndexChange, onClose }) {
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  useModalFocus({ dialogRef, initialFocusRef: closeRef, onEscape: onClose });
  const proof = proofs[index];
  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="Photo viewer"
      tabIndex={-1}
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center"
      onClick={onClose}
    >
      <IconButton
        ref={closeRef}
        onClick={onClose}
        variant="ghost"
        aria-label="Close photo viewer"
        className="absolute top-4 right-4 text-white/70 hover:text-white"
      >
        <X size={24} />
      </IconButton>
      {index > 0 && (
        <IconButton
          onClick={(e) => { e.stopPropagation(); onIndexChange(index - 1); }}
          variant="ghost"
          aria-label="Previous photo"
          className="absolute left-4 text-white/70 hover:text-white"
        >
          <ChevronLeft size={32} />
        </IconButton>
      )}
      {index < proofs.length - 1 && (
        <IconButton
          onClick={(e) => { e.stopPropagation(); onIndexChange(index + 1); }}
          variant="ghost"
          aria-label="Next photo"
          className="absolute right-4 text-white/70 hover:text-white"
        >
          <ChevronRight size={32} />
        </IconButton>
      )}
      <SwipeableImage
        src={proof.image}
        alt={proof.caption || `Proof ${index + 1}`}
        className="max-h-[85dvh] max-w-[90vw] object-contain rounded-lg"
        onPrev={index > 0 ? () => onIndexChange(index - 1) : undefined}
        onNext={index < proofs.length - 1 ? () => onIndexChange(index + 1) : undefined}
        onClose={onClose}
      />
      {proof.caption && (
        <p className="absolute bottom-6 text-white/80 text-body">{proof.caption}</p>
      )}
    </div>
  );
}
