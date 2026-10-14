import { useEffect, useRef, useState } from 'react';
import { ChevronDown, SlidersHorizontal } from 'lucide-react';
import { saveAvatarPreferences } from '../../api';
import { useAuth } from '../../hooks/useApi';
import Button from '../Button';
import ErrorAlert from '../ErrorAlert';
import { SelectField } from '../form';
import AvatarPreview from './AvatarPreview';
import { AVATAR_OPTIONS, AVATAR_WARDROBE_PRESETS, normalizeAvatarPreferences, sameAvatarPreferences } from '../../avatar/preferences';

const FIELDS = [
  ['hair_style', 'Hair style'],
  ['hair_color', 'Hair color'],
  ['skin_tone', 'Skin tone'],
  ['face_style', 'Face'],
  ['head_style', 'Ears'],
  ['outfit_style', 'Outfit style'],
  ['outfit', 'Outfit'],
];
const WARDROBE_FIELDS = [['headwear_style', 'Headwear'], ['mask_style', 'Mask'], ['bow_style', 'Bow'], ['quiver_style', 'Quiver']];

export default function AvatarCustomizer({ profile, onSaved }) {
  const { user } = useAuth();
  const saved = normalizeAvatarPreferences(profile.avatar_preferences);
  const [preferences, setPreferences] = useState(saved);
  const [editing, setEditing] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const activeIdentity = useRef(user?.id);
  const mounted = useRef(true);
  activeIdentity.current = user?.id;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const changed = !sameAvatarPreferences(saved, preferences);

  const update = (values) => {
    setPreferences((previous) => ({ ...previous, ...values }));
    setError('');
    setMessage('');
  };

  const save = async () => {
    const identity = user?.id;
    setWorking(true);
    setError('');
    setMessage('');
    try {
      const result = await saveAvatarPreferences(preferences);
      if (!mounted.current || activeIdentity.current !== identity) return;
      setPreferences(normalizeAvatarPreferences(result.avatar_preferences));
      onSaved(result);
      setMessage('Character saved.');
    } catch (error) {
      if (mounted.current && activeIdentity.current === identity) setError(error.message || 'Could not save your character. Try again.');
    } finally {
      if (mounted.current && activeIdentity.current === identity) setWorking(false);
    }
  };

  return (
    <section className="mt-4 space-y-3" aria-label="Your character">
      <div>
        <h2 className="font-body font-bold text-xl text-ink-primary">Your character</h2>
        <p className="font-body text-caption text-ink-secondary">Choose your character’s face, hair, skin tone, outfit and wardrobe.</p>
      </div>
      <AvatarPreview preferences={preferences} />
      <Button variant="secondary" size="sm" className="inline-flex items-center gap-2" aria-expanded={editing} onClick={() => setEditing((value) => !value)}>
        <SlidersHorizontal size={16} aria-hidden="true" /> Customize character <ChevronDown size={14} aria-hidden="true" />
      </Button>
      {editing && <div className="space-y-3 rounded-2xl border border-ink-page-shadow bg-ink-page-aged p-3">
        <div className="grid grid-cols-2 gap-3">
          {FIELDS.map(([key, label]) => <SelectField key={key} label={label} value={preferences[key]} disabled={working} onChange={(event) => update({ [key]: event.target.value })}>
            {AVATAR_OPTIONS[key].map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </SelectField>)}
        </div>
        <fieldset className="space-y-3 border-t border-ink-page-shadow pt-3" disabled={working}>
          <legend className="font-body font-bold text-lede text-ink-primary">Wardrobe</legend>
          <p className="font-body text-caption text-ink-secondary">Choose pieces individually or try a coordinated look.</p>
          <div className="flex flex-wrap gap-2">
            {AVATAR_WARDROBE_PRESETS.map((preset) => <Button key={preset.label} size="sm" variant="secondary" disabled={working}
              aria-pressed={Object.entries(preset.preferences).every(([key, value]) => preferences[key] === value)}
              onClick={() => update(preset.preferences)}>{preset.label}</Button>)}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {WARDROBE_FIELDS.map(([key, label]) => <SelectField key={key} label={label} value={preferences[key]} disabled={working}
              onChange={(event) => update({ [key]: event.target.value })}>
              {AVATAR_OPTIONS[key].map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </SelectField>)}
          </div>
        </fieldset>
        <ErrorAlert message={error} />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={save} disabled={!changed || working}>{working ? 'Saving…' : 'Save character'}</Button>
          <Button size="sm" variant="ghost" disabled={!changed || working} onClick={() => { setPreferences(saved); setError(''); setMessage(''); }}>Undo changes</Button>
        </div>
      </div>}
      {message && <p className="font-body text-body text-moss-deep" role="status">{message}</p>}
    </section>
  );
}
