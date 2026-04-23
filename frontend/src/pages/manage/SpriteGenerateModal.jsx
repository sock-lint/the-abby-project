import { useState } from 'react';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import Loader from '../../components/Loader';
import RpgSprite from '../../components/rpg/RpgSprite';
import { TextField, SelectField, TextAreaField } from '../../components/form';
import { generateSprite } from '../../api';

export const MOTION_OPTIONS = [
  'idle', 'walk', 'bounce', 'bubble', 'flicker', 'glow', 'wobble', 'sway',
];

export const FRAME_OPTIONS = [1, 2, 4, 6, 8];
export const TILE_OPTIONS = [32, 64, 128];
export const FPS_OPTIONS = [0, 4, 6, 8, 10, 12];

function defaultsFromSprite(sprite) {
  if (!sprite) {
    return {
      slug: '',
      prompt: '',
      motion: 'idle',
      frame_count: 1,
      tile_size: 64,
      fps: 0,
      pack: 'ai-generated',
      style_hint: '',
      reference_image_url: '',
      return_debug_raw: false,
    };
  }
  return {
    slug: sprite.slug,
    prompt: sprite.prompt || '',
    motion: sprite.motion || 'idle',
    frame_count: sprite.frame_count || 1,
    tile_size: sprite.tile_size || sprite.frame_width_px || 64,
    fps: sprite.fps || 0,
    pack: sprite.pack || 'ai-generated',
    style_hint: sprite.style_hint || '',
    reference_image_url: sprite.reference_image_url || '',
    return_debug_raw: false,
  };
}

/**
 * SpriteGenerateModal — parent-only modal for creating or replacing a sprite
 * via the Gemini pipeline.
 *
 * - mode="create": slug editable, overwrite=false (defaults). Caller supplies
 *   no `sprite` prop.
 * - mode="replace": slug disabled, overwrite=true, form pre-filled from the
 *   passed `sprite` row.
 */
export default function SpriteGenerateModal({ sprite, mode = 'create', onClose, onSuccess }) {
  const [form, setForm] = useState(() => defaultsFromSprite(sprite));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const isReplace = mode === 'replace';
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      const payload = {
        slug: form.slug,
        prompt: form.prompt,
        motion: form.motion,
        frame_count: Number(form.frame_count),
        tile_size: Number(form.tile_size),
        fps: Number(form.fps),
        pack: form.pack,
        style_hint: form.style_hint,
        reference_image_url: form.reference_image_url,
        return_debug_raw: form.return_debug_raw,
        overwrite: isReplace,
      };
      const resp = await generateSprite(payload);
      setResult(resp);
      if (onSuccess) onSuccess(resp);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    return (
      <BottomSheet
        title={isReplace ? 'Sprite replaced' : 'Sprite created'}
        onClose={onClose}
      >
        <div className="space-y-4 text-center">
          <div className="flex items-center justify-center h-24">
            <RpgSprite spriteKey={result.slug} size={96} alt={result.slug} />
          </div>
          <div className="text-sm text-ink-secondary">
            <div><code className="text-ink-primary">{result.slug}</code></div>
            <div className="text-tiny text-ink-whisper mt-1">
              {result.frame_count} frame{result.frame_count > 1 ? 's' : ''} · {result.frame_width_px}×{result.frame_height_px}px
            </div>
          </div>
          <Button variant="primary" onClick={onClose}>Close</Button>
        </div>
      </BottomSheet>
    );
  }

  return (
    <BottomSheet
      title={isReplace ? `Replace ${sprite.slug}` : 'Create sprite'}
      onClose={submitting ? undefined : onClose}
      disabled={submitting}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        {error && <ErrorAlert error={error} />}

        <TextField
          label="Slug"
          value={form.slug}
          onChange={(e) => set({ slug: e.target.value })}
          disabled={isReplace || submitting}
          required
          pattern="[a-z0-9][a-z0-9-]*"
          helpText="Lowercase a–z, digits, hyphens. e.g. fox-walk"
        />

        <TextAreaField
          label="Prompt"
          value={form.prompt}
          onChange={(e) => set({ prompt: e.target.value })}
          disabled={submitting}
          required
          rows={4}
          helpText="What Gemini should draw. Be specific about species, pose, colors."
        />

        <div className="grid grid-cols-2 gap-3">
          <SelectField
            label="Motion"
            value={form.motion}
            onChange={(e) => set({ motion: e.target.value })}
            disabled={submitting}
          >
            {MOTION_OPTIONS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </SelectField>
          <SelectField
            label="Frames"
            value={form.frame_count}
            onChange={(e) => {
              const fc = Number(e.target.value);
              set({ frame_count: fc, fps: fc === 1 ? 0 : (form.fps || 8) });
            }}
            disabled={submitting}
          >
            {FRAME_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </SelectField>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <SelectField
            label="Tile size"
            value={form.tile_size}
            onChange={(e) => set({ tile_size: Number(e.target.value) })}
            disabled={submitting}
          >
            {TILE_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}px</option>
            ))}
          </SelectField>
          <SelectField
            label="FPS"
            value={form.fps}
            onChange={(e) => set({ fps: Number(e.target.value) })}
            disabled={submitting || Number(form.frame_count) === 1}
            helpText={Number(form.frame_count) === 1 ? 'Static — fps must be 0' : undefined}
          >
            {FPS_OPTIONS.map((n) => (
              <option key={n} value={n}>{n === 0 ? 'static (0)' : n}</option>
            ))}
          </SelectField>
        </div>

        <TextField
          label="Pack"
          value={form.pack}
          onChange={(e) => set({ pack: e.target.value })}
          disabled={submitting}
        />

        <TextField
          label="Style hint (optional)"
          value={form.style_hint}
          onChange={(e) => set({ style_hint: e.target.value })}
          disabled={submitting}
          helpText="e.g. nes palette, 4-color gameboy"
        />

        <TextField
          label="Reference image URL (optional)"
          value={form.reference_image_url}
          onChange={(e) => set({ reference_image_url: e.target.value })}
          disabled={submitting}
          type="url"
          helpText="Paste another sprite's URL to anchor style + character"
        />

        <details className="text-sm">
          <summary className="cursor-pointer text-ink-whisper">Advanced</summary>
          <label className="mt-2 flex items-center gap-2 text-ink-secondary">
            <input
              type="checkbox"
              checked={form.return_debug_raw}
              onChange={(e) => set({ return_debug_raw: e.target.checked })}
              disabled={submitting}
            />
            Save raw Gemini + post-chroma images for debugging
          </label>
        </details>

        {submitting && (
          <div className="rounded-lg bg-ink-page-aged/60 p-3 text-center">
            <Loader />
            <div className="mt-2 text-xs text-ink-whisper">
              Calling Gemini — can take up to a minute.
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={submitting}>
            {isReplace ? 'Replace sprite' : 'Create sprite'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}
