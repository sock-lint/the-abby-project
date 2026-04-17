import { useState } from 'react';
import * as Sentry from '@sentry/react';
import { Camera, Send, X } from 'lucide-react';
import BottomSheet from './BottomSheet';
import SubjectBadge from './SubjectBadge';
import TimelinessBadge from './TimelinessBadge';
import ErrorAlert from './ErrorAlert';
import { submitHomework } from '../api';
import { downscaleImage } from '../utils/image';
import { buttonSuccess, formLabelClass } from '../constants/styles';
import { TextAreaField } from './form';

/**
 * HomeworkSubmitSheet — bottom-sheet form for submitting homework proof.
 * Extracted from Homework.jsx so the child dashboard can open the same
 * flow inline without navigating away.
 *
 * Controlled by the parent: pass `assignment` to open, `null` to close.
 */
export default function HomeworkSubmitSheet({ assignment, onClose, onSubmitted }) {
  const [images, setImages] = useState([]);
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

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

  // formLabelClass used directly for the photo-picker grid label below — that
  // field isn't a single <input>, so it can't use the form-primitive
  // label/htmlFor wiring; the className stays in lockstep via the constant.

  return (
    <BottomSheet onClose={handleClose} title="Affix photographic evidence">
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
          <label className={formLabelClass}>Proof photos (required)</label>
          <div className="flex gap-2 flex-wrap">
            {images.map((img, i) => (
              <div key={i} className="relative w-16 h-16 rounded-lg overflow-hidden border border-ink-page-shadow">
                <img src={URL.createObjectURL(img)} alt="" className="w-full h-full object-cover" />
                <button
                  type="button"
                  onClick={() => setImages(images.filter((_, j) => j !== i))}
                  aria-label="Remove photo"
                  className="absolute top-0 right-0 bg-ink-primary/80 rounded-bl-lg p-0.5 text-ink-page-rune-glow"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
            <label className="w-16 h-16 rounded-lg border-2 border-dashed border-ink-page-shadow hover:border-sheikah-teal/60 flex items-center justify-center cursor-pointer transition-colors">
              <Camera size={20} className="text-ink-secondary" />
              <input
                type="file" accept="image/*" multiple className="hidden"
                onChange={(e) => setImages([...images, ...Array.from(e.target.files)])}
              />
            </label>
          </div>
        </div>

        <TextAreaField
          placeholder="Notes (optional)" value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
        />

        {error && <ErrorAlert message={error} />}

        <button
          type="button"
          onClick={handleSubmit}
          disabled={!images.length || submitting}
          className={`w-full py-2.5 text-sm flex items-center justify-center gap-2 ${buttonSuccess}`}
        >
          <Send size={16} /> {submitting ? 'Submitting…' : 'Submit for review'}
        </button>
      </div>
    </BottomSheet>
  );
}
