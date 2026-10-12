import { useId, useState } from 'react';
import * as Sentry from '@sentry/react';
import { Camera, Send, X } from 'lucide-react';
import BottomSheet from './BottomSheet';
import SubjectBadge from './SubjectBadge';
import TimelinessBadge from './TimelinessBadge';
import ErrorAlert from './ErrorAlert';
import { submitHomework } from '../api';
import { downscaleImage } from '../utils/image';
import { formLabelClass } from '../constants/styles';
import Button from './Button';
import { TextAreaField } from './form';

/**
 * HomeworkSubmitSheet — bottom-sheet form for submitting homework proof.
 * Extracted from pages/Homework/index.jsx so the child dashboard can open the same
 * flow inline without navigating away.
 *
 * Controlled by the parent: pass `assignment` to open, `null` to close.
 */
export default function HomeworkSubmitSheet({ assignment, onClose, onSubmitted }) {
  const [images, setImages] = useState([]);
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const proofInputId = useId();

  if (!assignment) return null;

  const reset = () => {
    setImages([]);
    setNotes('');
    setError('');
  };

  const handleClose = () => {
    reset();
    onClose?.();
  };

  const handleSubmit = async () => {
    if (!images.length) return;
    setSubmitting(true);
    setError('');
    try {
      const downscaled = await Promise.all(images.map((img) => downscaleImage(img)));
      const fd = new FormData();
      downscaled.forEach((img) => fd.append('images', img));
      if (notes) fd.append('notes', notes);
      await submitHomework(assignment.id, fd);
      reset();
      onSubmitted?.();
    } catch (err) {
      Sentry.captureException(err, { tags: { area: 'homework.submit' } });
      setError(err?.message || 'Could not submit. Try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // formLabelClass used directly for the photo-picker grid label below — the
  // picker isn't a form-primitive field, so the label/htmlFor wiring is done by
  // hand (proofInputId); the className stays in lockstep via the constant.

  return (
    <BottomSheet
      onClose={handleClose}
      title="Affix photographic evidence"
      disabled={submitting}
      dirty={images.length > 0 || Boolean(notes)}
      // Sticky footer so the submit button stays reachable while the notes
      // field has focus — the on-screen keyboard overlays the sheet rather
      // than shrinking it, burying anything parked at the end of the scroller.
      footer={(
        <Button
          variant="success"
          size="sm"
          onClick={handleSubmit}
          disabled={!images.length || submitting}
          className="w-full flex items-center justify-center gap-2"
        >
          <Send size={16} /> {submitting ? 'Submitting…' : 'Submit for review'}
        </Button>
      )}
    >
      <div className="space-y-4">
        <div>
          <h3 className="font-display text-lg text-ink-primary">{assignment.title}</h3>
          <div className="flex gap-2 mt-1">
            {assignment.subject && <SubjectBadge subject={assignment.subject} />}
            {assignment.timeliness_preview && (
              <TimelinessBadge timeliness={assignment.timeliness_preview.timeliness} />
            )}
          </div>
        </div>

        <div>
          <label htmlFor={proofInputId} className={formLabelClass}>Proof photos (required)</label>
          <div className="flex gap-2 flex-wrap">
            {images.map((img, i) => (
              <div key={i} className="relative w-16 h-16 rounded-lg overflow-hidden border border-ink-page-shadow">
                <img src={URL.createObjectURL(img)} alt="" className="w-full h-full object-cover" />
                {/* intentional: corner-flush remove badge on the photo
                    thumbnail. IconButton's default padding + rounding
                    breaks the in-image overlay shape.
                    The button itself is a transparent 44px box anchored to
                    the corner — the badge alone was a ~17px target, so a kid
                    correcting a mis-picked photo mostly missed it. Nothing
                    else on the thumbnail is tappable, so the larger hit area
                    costs no competing target. */}
                <button
                  type="button"
                  onClick={() => setImages(images.filter((_, j) => j !== i))}
                  aria-label="Remove photo"
                  className="absolute top-0 right-0 min-h-11 min-w-11 flex items-start justify-end"
                >
                  <span className="flex bg-ink-primary/80 rounded-bl-lg p-0.5 text-ink-page-rune-glow">
                    <X size={12} />
                  </span>
                </button>
              </div>
            ))}
            <label className="w-16 h-16 rounded-lg border-2 border-dashed border-ink-page-shadow hover:border-sheikah-teal/60 flex items-center justify-center cursor-pointer transition-colors focus-within:ring-2 focus-within:ring-sheikah-teal-deep focus-within:ring-offset-2 focus-within:ring-offset-ink-page">
              <Camera size={20} className="text-ink-secondary" aria-hidden="true" />
              {/* intentional: file picker label/input pattern — design-system
                  primitives don't yet wrap multi-file native pickers. The
                  input is sr-only, not display:none, so it stays in the tab
                  order; the tile's focus-within ring is its focus indicator. */}
              <input
                id={proofInputId}
                type="file" accept="image/*" multiple className="sr-only"
                aria-label="Add proof photos (required)"
                onChange={(e) => setImages([...images, ...Array.from(e.target.files)])}
              />
            </label>
          </div>
        </div>

        <TextAreaField
          label="Notes (optional)"
          placeholder="Notes (optional)" value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
        />

        {error && <ErrorAlert message={error} />}
      </div>
    </BottomSheet>
  );
}
