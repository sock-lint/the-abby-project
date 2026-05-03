import * as Sentry from '@sentry/react';
import { createHomework, updateHomework } from '../../api';
import { useFormState } from '../../hooks/useFormState';
import BottomSheet from '../../components/BottomSheet';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';
import { TextField, SelectField, TextAreaField } from '../../components/form';
import { quickDueDates } from '../../utils/dates';

const SUBJECTS = [
  { value: 'math', label: 'Math' },
  { value: 'reading', label: 'Reading' },
  { value: 'writing', label: 'Writing' },
  { value: 'science', label: 'Science' },
  { value: 'social_studies', label: 'Social Studies' },
  { value: 'art', label: 'Art' },
  { value: 'music', label: 'Music' },
  { value: 'other', label: 'Other' },
];

export default function HomeworkFormModal({
  assignment, isParent, children: childrenList = [], onClose, onSaved,
}) {
  const isEdit = !!assignment;
  const { form, set, saving, setSaving, error, setError } = useFormState({
    title: assignment?.title || '',
    description: assignment?.description || '',
    subject: assignment?.subject || 'math',
    effort_level: assignment?.effort_level ?? 3,
    due_date: assignment?.due_date || '',
    assigned_to: assignment?.assigned_to ?? '',
  });

  const presets = quickDueDates();
  const rawChips = [
    { label: 'Tomorrow', value: presets.tomorrow, relative: true },
    { label: 'Friday', value: presets.friday, relative: false },
    { label: 'Next Mon', value: presets.nextMonday, relative: false },
    { label: '+1 week', value: presets.nextWeek, relative: true },
  ];
  const presetChips = rawChips.filter((c, i, arr) =>
    c.relative || !arr.some((o, j) => j !== i && o.relative && o.value === c.value),
  );

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isParent && !form.assigned_to) {
      setError('Please select a child to assign this to.');
      return;
    }
    const payload = {
      title: form.title,
      description: form.description,
      subject: form.subject,
      due_date: form.due_date,
    };
    if (isParent) {
      payload.effort_level = parseInt(form.effort_level);
      if (form.assigned_to) {
        payload.assigned_to = parseInt(form.assigned_to);
      }
    }
    setSaving(true);
    setError(null);
    try {
      if (isEdit) {
        await updateHomework(assignment.id, payload);
      } else {
        await createHomework(payload);
      }
      onSaved();
    } catch (err) {
      Sentry.captureException(err, {
        tags: { area: isEdit ? 'homework.update' : 'homework.create' },
      });
      setError(err?.message || (isEdit
        ? 'Could not update the assignment.'
        : 'Could not create the assignment.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet
      title={isEdit ? 'Edit assignment' : 'New assignment'}
      onClose={onClose}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <TextField
          type="text" placeholder="Title" required value={form.title}
          onChange={(e) => set({ title: e.target.value })}
        />
        <TextAreaField
          placeholder="Description (optional)" value={form.description}
          onChange={(e) => set({ description: e.target.value })}
          rows={2}
        />
        <div>
          <span className="font-script text-sm text-ink-secondary mb-1 block">Due</span>
          {!isEdit && (
            <div className="flex flex-wrap gap-2 mb-2">
              {presetChips.map((chip) => {
                const active = form.due_date === chip.value;
                return (
                  <button
                    key={chip.label}
                    type="button"
                    aria-pressed={active}
                    onClick={() => set({ due_date: chip.value })}
                    className={
                      'px-3 py-1 text-xs font-medium rounded-full border transition-colors ' +
                      (active
                        ? 'bg-sheikah-teal-deep text-ink-page-rune-glow border-sheikah-teal-deep'
                        : 'bg-ink-page-aged text-ink-secondary border-ink-page-shadow hover:text-ink-primary')
                    }
                  >
                    {chip.label}
                  </button>
                );
              })}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <SelectField
              value={form.subject}
              onChange={(e) => set({ subject: e.target.value })}
            >
              {SUBJECTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </SelectField>
            <TextField
              type="date" required value={form.due_date}
              onChange={(e) => set({ due_date: e.target.value })}
            />
          </div>
        </div>
        {isParent && (
          <TextField
            label="Effort (1-5)"
            type="number" min={1} max={5} value={form.effort_level}
            onChange={(e) => set({ effort_level: e.target.value })}
            helpText="Weights XP distribution across skill tags — no money or coins."
          />
        )}
        {!isParent && !isEdit && (
          <p className="font-script text-xs text-ink-whisper italic">
            Log it here so your grown-ups can see — you'll earn XP, streaks,
            and a chance at loot for every assignment you share.
          </p>
        )}
        {isParent && childrenList.length > 0 && (
          <SelectField
            label="Assign to"
            value={form.assigned_to} required
            onChange={(e) => set({ assigned_to: e.target.value })}
          >
            <option value="">Choose a child…</option>
            {childrenList.map((c) => (
              <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
            ))}
          </SelectField>
        )}
        {isParent && childrenList.length === 0 && (
          <p className="font-script text-sm text-ember-deep italic">
            No children registered yet — add one in <a href="/manage" className="underline">Manage</a> before creating homework.
          </p>
        )}
        {error && <ErrorAlert message={error} />}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button" onClick={onClose}
            className="px-4 py-2 text-sm text-ink-secondary hover:text-ink-primary transition-colors"
          >
            Cancel
          </button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving ? 'Saving…' : isEdit ? 'Update assignment' : 'Create assignment'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}
