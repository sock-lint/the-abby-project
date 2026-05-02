import Button from './Button';

/**
 * ModalActions — Cancel + Submit row for form modals.
 *
 * The same `<button variant="secondary">Cancel</button> + <button type="submit">Save</button>`
 * pair sits at the bottom of every domain form modal (chore, habit, child,
 * reward, homework, …). Centralizing it keeps spacing/disabled-state/saving-
 * label behavior in lockstep across every flow.
 */
export default function ModalActions({
  onClose,
  submitLabel = 'Save',
  savingLabel = 'Saving…',
  saving = false,
  cancelLabel = 'Cancel',
  size = 'sm',
  className = '',
}) {
  return (
    <div className={`flex justify-end gap-2 pt-2 ${className}`}>
      <Button
        type="button"
        variant="ghost"
        size={size}
        onClick={onClose}
        disabled={saving}
      >
        {cancelLabel}
      </Button>
      <Button type="submit" size={size} disabled={saving}>
        {saving ? savingLabel : submitLabel}
      </Button>
    </div>
  );
}
