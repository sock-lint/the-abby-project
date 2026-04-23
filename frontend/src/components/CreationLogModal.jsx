import { useMemo, useState } from 'react';
import { Music, Image as ImageIcon } from 'lucide-react';
import BottomSheet from './BottomSheet';
import Button from './Button';
import ErrorAlert from './ErrorAlert';
import { TextAreaField } from './form';
import { formLabelClass } from '../constants/styles';
import { useApi } from '../hooks/useApi';
import { normalizeList } from '../utils/api';
import { downscaleImage } from '../utils/image';
import { createCreation, getSkills } from '../api';

// Creative-subset allow-list — must match apps/creations/constants.py.
const CREATIVE_CATEGORY_NAMES = new Set([
  'Art & Crafts',
  'Making & Fabrication',
  'Music',
  'Cooking',
  'Creative Writing',
  'Sewing & Textiles',
  'Woodworking',
]);

const MAX_AUDIO_BYTES = 10 * 1024 * 1024; // 10 MB

export default function CreationLogModal({ onClose, onSaved }) {
  const { data: skillsData, loading: skillsLoading } = useApi(getSkills);
  const skills = normalizeList(skillsData).filter((s) =>
    CREATIVE_CATEGORY_NAMES.has(s.category_name)
  );

  // Group by category for the <optgroup> rendering.
  const skillsByCategory = useMemo(() => {
    const grouped = new Map();
    for (const skill of skills) {
      if (!grouped.has(skill.category_name)) {
        grouped.set(skill.category_name, []);
      }
      grouped.get(skill.category_name).push(skill);
    }
    return [...grouped.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [skills]);

  const [image, setImage] = useState(null);
  const [audio, setAudio] = useState(null);
  const [caption, setCaption] = useState('');
  const [primary, setPrimary] = useState('');
  const [secondary, setSecondary] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const canSubmit = image && primary && !saving;

  const handleImage = (e) => {
    const f = e.target.files?.[0] || null;
    setImage(f);
  };
  const handleAudio = (e) => {
    const f = e.target.files?.[0] || null;
    if (f && f.size > MAX_AUDIO_BYTES) {
      setError('Audio file is too big — please pick one under 10 MB.');
      return;
    }
    setError('');
    setAudio(f);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError('');
    try {
      const fd = new FormData();
      const downscaled = await downscaleImage(image, { maxDim: 2048 });
      fd.append('image', downscaled);
      if (audio) fd.append('audio', audio);
      if (caption) fd.append('caption', caption);
      fd.append('primary_skill_id', String(primary));
      if (secondary) fd.append('secondary_skill_id', String(secondary));
      const saved = await createCreation(fd);
      onSaved?.(saved);
      onClose?.();
    } catch (err) {
      setError(err?.message || 'Could not log your creation.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Log a creation" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <label className={formLabelClass}>
          Photo (required)
          <input
            type="file"
            accept="image/*"
            onChange={handleImage}
            className="mt-1 block w-full text-sm"
          />
        </label>
        {image && (
          <div className="flex items-center gap-2 text-xs text-ink-whisper font-script">
            <ImageIcon size={14} /> {image.name}
          </div>
        )}

        <label className={formLabelClass}>
          Audio (optional)
          <span className="ml-1 text-xs text-ink-whisper font-script">— up to 10 MB</span>
          <input
            type="file"
            accept="audio/*"
            onChange={handleAudio}
            className="mt-1 block w-full text-sm"
          />
        </label>
        {audio && (
          <div className="flex items-center gap-2 text-xs text-ink-whisper font-script">
            <Music size={14} /> {audio.name}
          </div>
        )}

        <TextAreaField
          id="creation-caption"
          label="Caption (optional)"
          value={caption}
          onChange={(e) => setCaption(e.target.value.slice(0, 200))}
          placeholder="What did you make?"
          rows={2}
        />

        <label className={formLabelClass}>
          Primary skill (required)
          <select
            value={primary}
            onChange={(e) => {
              setPrimary(e.target.value);
              if (e.target.value === secondary) setSecondary('');
            }}
            className="mt-1 block w-full rounded-lg border border-ink-page-shadow bg-ink-page px-3 py-2 text-sm"
            disabled={skillsLoading}
          >
            <option value="">Choose one…</option>
            {skillsByCategory.map(([catName, catSkills]) => (
              <optgroup key={catName} label={catName}>
                {catSkills.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>

        <label className={formLabelClass}>
          Secondary skill (optional)
          <select
            value={secondary}
            onChange={(e) => setSecondary(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-ink-page-shadow bg-ink-page px-3 py-2 text-sm"
            disabled={skillsLoading || !primary}
          >
            <option value="">None</option>
            {skillsByCategory.map(([catName, catSkills]) => (
              <optgroup key={catName} label={catName}>
                {catSkills
                  .filter((s) => String(s.id) !== primary)
                  .map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
              </optgroup>
            ))}
          </select>
        </label>

        {error && <ErrorAlert message={error} />}

        <div className="flex gap-2 pt-1">
          <Button variant="secondary" type="button" onClick={onClose} className="flex-1">
            Cancel
          </Button>
          <Button type="submit" disabled={!canSubmit} className="flex-1">
            {saving ? 'Saving…' : 'Log creation'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}
