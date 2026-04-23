import { useState } from 'react';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorAlert from '../../components/ErrorAlert';
import Loader from '../../components/Loader';
import RpgSprite from '../../components/rpg/RpgSprite';
import SpriteGenerateModal from './SpriteGenerateModal';
import {
  rerollSprite,
  updateSpriteMeta,
  deleteSprite as apiDeleteSprite,
} from '../../api';

const REROLL_COST_PER_FRAME = 0.04;

function formatCost(frameCount) {
  const n = Math.max(1, Number(frameCount) || 1);
  return `$${(n * REROLL_COST_PER_FRAME).toFixed(2)}`;
}

function Row({ label, value, mono }) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <span className="text-ink-whisper">{label}</span>
      <span className={`text-ink-primary ${mono ? 'font-mono text-xs' : ''} text-right`}>
        {value}
      </span>
    </div>
  );
}

export default function SpriteDetailSheet({ sprite, onClose, onChanged }) {
  const [confirmReroll, setConfirmReroll] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editingMeta, setEditingMeta] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const canReroll = Boolean(sprite.prompt);

  const runReroll = async () => {
    setConfirmReroll(false);
    setBusy(true);
    setError(null);
    try {
      await rerollSprite(sprite.slug);
      if (onChanged) await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const runDelete = async () => {
    setConfirmDelete(false);
    setBusy(true);
    setError(null);
    try {
      await apiDeleteSprite(sprite.slug);
      if (onChanged) await onChanged();
      onClose();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  if (replacing) {
    return (
      <SpriteGenerateModal
        sprite={sprite}
        mode="replace"
        onClose={() => setReplacing(false)}
        onSuccess={async () => {
          setReplacing(false);
          if (onChanged) await onChanged();
        }}
      />
    );
  }

  if (editingMeta) {
    return (
      <EditMetadataSheet
        sprite={sprite}
        onCancel={() => setEditingMeta(false)}
        onSaved={async () => {
          setEditingMeta(false);
          if (onChanged) await onChanged();
        }}
      />
    );
  }

  return (
    <>
      <BottomSheet title={sprite.slug} onClose={busy ? undefined : onClose} disabled={busy}>
        <div className="space-y-4">
          <div className="flex items-center justify-center h-28">
            <RpgSprite spriteKey={sprite.slug} size={112} alt={sprite.slug} />
          </div>

          {error && <ErrorAlert error={error} />}
          {busy && (
            <div className="rounded-lg bg-ink-page-aged/60 p-3 text-center">
              <Loader />
              <div className="mt-2 text-xs text-ink-whisper">Working — Gemini calls take up to a minute.</div>
            </div>
          )}

          <div className="space-y-1.5">
            <Row label="Pack" value={sprite.pack} />
            <Row
              label="Frames"
              value={`${sprite.frame_count} · ${sprite.frame_width_px}×${sprite.frame_height_px}px · ${sprite.frame_count > 1 ? `${sprite.fps} fps` : 'static'}`}
            />
            {sprite.created_by_name && <Row label="Created by" value={sprite.created_by_name} />}
          </div>

          <details className="text-sm" open>
            <summary className="cursor-pointer text-ink-whisper mb-2">Authoring inputs</summary>
            <div className="space-y-1.5 pl-2">
              <Row
                label="Prompt"
                value={sprite.prompt || <em className="text-ink-whisper">— not recorded —</em>}
                mono
              />
              <Row label="Motion" value={sprite.motion || <em className="text-ink-whisper">—</em>} />
              <Row
                label="Style hint"
                value={sprite.style_hint || <em className="text-ink-whisper">—</em>}
              />
              <Row
                label="Tile size"
                value={sprite.tile_size ? `${sprite.tile_size}px` : <em className="text-ink-whisper">—</em>}
              />
              <Row
                label="Reference URL"
                value={sprite.reference_image_url || <em className="text-ink-whisper">—</em>}
                mono
              />
            </div>
          </details>

          <div className="flex flex-wrap justify-end gap-2 pt-2">
            <Button
              variant="danger"
              size="sm"
              onClick={() => setConfirmDelete(true)}
              disabled={busy}
            >
              Delete
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setEditingMeta(true)}
              disabled={busy}
            >
              Edit metadata
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setReplacing(true)}
              disabled={busy}
            >
              Replace
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setConfirmReroll(true)}
              disabled={busy || !canReroll}
              title={canReroll ? undefined : 'No stored prompt — use Replace instead'}
            >
              Reroll
            </Button>
          </div>
        </div>
      </BottomSheet>

      {confirmReroll && (
        <ConfirmDialog
          title={`Reroll ${sprite.slug}?`}
          message={`This re-runs the saved prompt through Gemini and replaces the current image. Approximate cost: ${formatCost(sprite.frame_count)}.`}
          confirmLabel="Reroll"
          onConfirm={runReroll}
          onCancel={() => setConfirmReroll(false)}
        />
      )}
      {confirmDelete && (
        <ConfirmDialog
          title={`Delete ${sprite.slug}?`}
          message="This removes the Ceph blob and the DB row. Anything referencing this sprite will fall back to its icon."
          confirmLabel="Delete"
          onConfirm={runDelete}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </>
  );
}

function EditMetadataSheet({ sprite, onCancel, onSaved }) {
  const [pack, setPack] = useState(sprite.pack);
  const [fps, setFps] = useState(sprite.fps);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await updateSpriteMeta(sprite.slug, { pack, fps: Number(fps) });
      await onSaved();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <BottomSheet title={`Edit ${sprite.slug}`} onClose={busy ? undefined : onCancel} disabled={busy}>
      <form onSubmit={submit} className="space-y-3">
        {error && <ErrorAlert error={error} />}
        <label className="block text-sm">
          <span className="block mb-1 text-ink-secondary">Pack</span>
          <input
            className="w-full px-3 py-2 rounded border border-ink-page-shadow bg-ink-page text-ink-primary"
            value={pack}
            onChange={(e) => setPack(e.target.value)}
            disabled={busy}
          />
        </label>
        <label className="block text-sm">
          <span className="block mb-1 text-ink-secondary">FPS</span>
          <input
            type="number"
            min={0}
            max={30}
            className="w-full px-3 py-2 rounded border border-ink-page-shadow bg-ink-page text-ink-primary"
            value={fps}
            onChange={(e) => setFps(e.target.value)}
            disabled={busy}
          />
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={busy}>Save</Button>
        </div>
      </form>
    </BottomSheet>
  );
}
