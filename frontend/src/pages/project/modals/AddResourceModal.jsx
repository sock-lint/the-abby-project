import { createResource } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import ErrorAlert from '../../../components/ErrorAlert';
import { useFormState } from '../../../hooks/useFormState';
import Button from '../../../components/Button';
import { TextField, SelectField } from '../../../components/form';

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
        <TextField
          label="URL"
          value={form.url}
          onChange={onField('url')}
          type="url"
          placeholder="https://..."
          required
          autoFocus
        />
        <TextField label="Title (optional)" value={form.title} onChange={onField('title')} />
        <div className="grid grid-cols-2 gap-3">
          <SelectField label="Type" value={form.resource_type} onChange={onField('resource_type')}>
            <option value="link">Link</option>
            <option value="video">Video</option>
            <option value="doc">Document</option>
            <option value="image">Image</option>
          </SelectField>
          <SelectField label="Attach to Step" value={form.step} onChange={onField('step')}>
            <option value="">(Project-level)</option>
            {steps.map((s, idx) => (
              <option key={s.id} value={s.id}>
                {idx + 1}. {s.title.slice(0, 40)}
              </option>
            ))}
          </SelectField>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose} disabled={saving} className="flex-1">
            Cancel
          </Button>
          <Button type="submit" disabled={saving || !form.url.trim()} className="flex-1">
            {saving ? 'Adding...' : 'Add Resource'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}
