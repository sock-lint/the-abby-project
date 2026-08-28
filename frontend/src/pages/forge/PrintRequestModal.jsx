import { useRef, useState } from 'react';
import { Box, Link2, Upload } from 'lucide-react';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import ModalActions from '../../components/ModalActions';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { DateField, TextAreaField, TextField } from '../../components/form';
import { createPrintRequest, previewPrintLink } from '../../api';
import { quickDueDates } from '../../utils/dates';

const DUE_CHIPS = [
  { key: 'tomorrow', label: 'Tomorrow' },
  { key: 'friday', label: 'Friday' },
  { key: 'nextWeek', label: 'Next week' },
];

/**
 * PrintRequestModal — the child's "please print this" form.
 *
 * Two source shapes, one submit: a model-host link (MakerWorld / Printables
 * / Thingiverse / anywhere) or an uploaded model file. Links go up as JSON;
 * an upload switches to multipart, which is why `createPrintRequest` accepts
 * either an object or a FormData.
 *
 * The link preview is deliberately soft. `POST /print-requests/preview/`
 * scrapes OpenGraph tags server-side, and model hosts are slow, rate-limit,
 * and change their markup. A failed scrape renders as a hint, never as a
 * blocker — the child can still submit, and `enrich_request_metadata` gets
 * another shot at the title and thumbnail after the row exists.
 */
export default function PrintRequestModal({ onClose, onSaved }) {
  const [mode, setMode] = useState('link'); // 'link' | 'upload'
  const [url, setUrl] = useState('');
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [color, setColor] = useState('');
  const [reason, setReason] = useState('');
  const [neededBy, setNeededBy] = useState('');

  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Which URL we last scraped, so a blur that didn't change anything doesn't
  // re-hit a host that may be rate-limiting us.
  const previewedRef = useRef('');
  const dueDates = quickDueDates();

  const runPreview = async (candidate) => {
    const value = (candidate || '').trim();
    if (!value || !/^https?:\/\//i.test(value)) return;
    if (previewedRef.current === value) return;
    previewedRef.current = value;
    setPreviewing(true);
    try {
      const meta = await previewPrintLink(value);
      setPreview(meta);
      if (meta?.title && !title) setTitle(meta.title);
    } catch (err) {
      // Even the preview endpoint failing outright is a hint, not a stop.
      setPreview({ error: err?.message || 'Could not read that link.' });
    } finally {
      setPreviewing(false);
    }
  };

  const handlePaste = (e) => {
    const pasted = e.clipboardData?.getData('text');
    if (pasted) {
      setUrl(pasted);
      runPreview(pasted);
    }
  };

  const canSubmit = Boolean(
    color.trim() && reason.trim() && (mode === 'link' ? url.trim() : file) && !saving,
  );

  const submit = async (e) => {
    if (e?.preventDefault) e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError('');
    try {
      let payload;
      if (mode === 'upload' && file) {
        payload = new FormData();
        payload.append('model_file', file);
        payload.append('title', title.trim() || file.name);
        payload.append('color', color.trim());
        payload.append('reason', reason.trim());
        if (neededBy) payload.append('needed_by', neededBy);
      } else {
        payload = {
          title: title.trim(),
          source_url: url.trim(),
          color: color.trim(),
          reason: reason.trim(),
          needed_by: neededBy || null,
        };
      }
      const saved = await createPrintRequest(payload);
      onSaved?.(saved);
      onClose?.();
    } catch (err) {
      setError(err?.message || 'Could not send that request.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet
      title="Ask for a print"
      onClose={onClose}
      disabled={saving}
      dirty={Boolean(url || file || title || color || reason || neededBy)}
    >
      <form onSubmit={submit} className="space-y-3">
        <div className="flex gap-2" role="group" aria-label="Where the model comes from">
          <Button
            variant={mode === 'link' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setMode('link')}
            aria-pressed={mode === 'link'}
            className="flex-1 flex items-center justify-center gap-1"
          >
            <Link2 size={14} /> Link
          </Button>
          <Button
            variant={mode === 'upload' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setMode('upload')}
            aria-pressed={mode === 'upload'}
            className="flex-1 flex items-center justify-center gap-1"
          >
            <Upload size={14} /> Upload
          </Button>
        </div>

        {mode === 'link' ? (
          <TextField
            id="forge-url"
            label="Link to the model"
            type="url"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onBlur={(e) => runPreview(e.target.value)}
            onPaste={handlePaste}
            placeholder="https://makerworld.com/en/models/…"
            helpText="MakerWorld, Printables, Thingiverse — or any model page."
          />
        ) : (
          <div>
            {/* intentional: native file picker markup — the form primitives
                don't wrap <input type="file">, same retention the ingest
                and photo-upload flows carry. */}
            <label htmlFor="forge-file" className="font-script text-body text-ink-secondary mb-1 block">
              Model file
            </label>
            <input
              id="forge-file"
              type="file"
              accept=".stl,.3mf,.step,.stp,.obj"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="w-full text-body text-ink-secondary file:mr-3 file:rounded-lg file:border file:border-ink-page-shadow file:bg-ink-page-aged file:px-3 file:py-1.5 file:text-body file:text-ink-primary"
            />
            <p className="text-caption text-ink-whisper mt-1">
              STL, 3MF, STEP or OBJ.
            </p>
          </div>
        )}

        {mode === 'link' && (previewing || preview) && (
          <ParchmentCard tone="deep" className="!p-3">
            {previewing ? (
              <div className="font-script text-caption text-ink-whisper">Reading the link…</div>
            ) : (
              <div className="flex gap-3 items-center">
                {preview.thumbnail_url ? (
                  <img
                    src={preview.thumbnail_url}
                    alt=""
                    className="w-12 h-12 rounded object-cover border border-ink-page-shadow shrink-0"
                  />
                ) : (
                  <div
                    aria-hidden="true"
                    className="w-12 h-12 rounded border border-ink-page-shadow flex items-center justify-center text-ink-whisper shrink-0"
                  >
                    <Box size={18} />
                  </div>
                )}
                <div className="min-w-0">
                  <div className="font-display text-body text-ink-primary truncate">
                    {preview.title || 'Untitled model'}
                  </div>
                  {preview.author && (
                    <div className="font-script text-caption text-ink-whisper truncate">
                      by {preview.author}
                    </div>
                  )}
                  {preview.error && (
                    <div className="font-script text-caption text-ink-whisper">
                      Couldn’t read the page — you can still send this.
                    </div>
                  )}
                </div>
              </div>
            )}
          </ParchmentCard>
        )}

        <TextField
          id="forge-title"
          label="What is it?"
          value={title}
          onChange={(e) => setTitle(e.target.value.slice(0, 160))}
          placeholder="Articulated dragon"
          helpText="We fill this in from the link when we can."
        />

        <TextField
          id="forge-color"
          label="Colour"
          value={color}
          onChange={(e) => setColor(e.target.value.slice(0, 40))}
          placeholder="Glow in the dark green"
        />

        <TextAreaField
          id="forge-reason"
          label="Why do you want it?"
          value={reason}
          onChange={(e) => setReason(e.target.value.slice(0, 2000))}
          placeholder="It's a present for Nana's birthday."
          rows={3}
          helpText="Say what it's for — this is what your parent reads first."
        />

        <div>
          <DateField
            id="forge-needed-by"
            label="When do you need it?"
            value={neededBy}
            onChange={(e) => setNeededBy(e.target.value)}
          />
          <div className="flex flex-wrap gap-2 mt-2">
            {DUE_CHIPS.map((chip) => (
              <Button
                key={chip.key}
                variant="secondary"
                size="sm"
                onClick={() => setNeededBy(dueDates[chip.key])}
              >
                {chip.label}
              </Button>
            ))}
          </div>
        </div>

        {error && <ErrorAlert message={error} />}

        <ModalActions
          fullWidth
          onClose={onClose}
          submitLabel="Send request"
          savingLabel="Sending…"
          saving={saving}
          submitDisabled={!canSubmit}
        />
      </form>
    </BottomSheet>
  );
}
