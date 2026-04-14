import { createResource } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import ErrorAlert from '../../../components/ErrorAlert';
import { useFormState } from '../../../hooks/useFormState';
import { buttonPrimary, buttonSecondary, inputClass } from '../../../constants/styles';

export default function AddResourceModal({ projectId, steps, onClose, onSaved }) {
  const { form, set, saving, setSaving, error, setError } = useFormState({
    title: '',
    url: '',
    resource_type: 'link',
    step: '',
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createResource(projectId, {
        project: projectId,
        title: form.title,
        url: form.url,
        resource_type: form.resource_type,
        step: form.step || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Resource" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-ink-whisper mb-1">URL</label>
          <input
            value={form.url}
            onChange={onField('url')}
            className={inputClass}
            type="url"
            placeholder="https://..."
            required
            autoFocus
          />
        </div>
        <div>
          <label className="block text-xs text-ink-whisper mb-1">Title (optional)</label>
          <input value={form.title} onChange={onField('title')} className={inputClass} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Type</label>
            <select value={form.resource_type} onChange={onField('resource_type')} className={inputClass}>
              <option value="link">Link</option>
              <option value="video">Video</option>
              <option value="doc">Document</option>
              <option value="image">Image</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Attach to Step</label>
            <select value={form.step} onChange={onField('step')} className={inputClass}>
              <option value="">(Project-level)</option>
              {steps.map((s, idx) => (
                <option key={s.id} value={s.id}>
                  {idx + 1}. {s.title.slice(0, 40)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className={`flex-1 py-3 ${buttonSecondary}`}>
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.url.trim()} className={`flex-1 py-3 ${buttonPrimary}`}>
            {saving ? 'Adding...' : 'Add Resource'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}
