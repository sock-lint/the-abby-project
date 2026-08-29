import Button from './Button';

/**
 * ModalActions — Cancel + Submit row for form modals.
 *
 * The same `Cancel` + `Save` pair sits at the bottom of every domain form
 * modal (chore, habit, creation, movement session, printer, …). Centralizing
 * it keeps order, sizing, disabled-state and saving-label behavior in lockstep
 * across every flow instead of drifting per sheet.
 *
 * Two layouts:
 *   default          — right-aligned `sm` pair. Compact desktop-leaning forms.
 *   fullWidth        — two `md` buttons splitting the row 50/50, which is the
 *                      thumb-friendly shape for a phone sheet. Cancel goes
 *                      `secondary` here: a ghost half of a split row reads as
 *                      disabled next to a filled one.
 *
 * `formId` associates the submit button with a `<form id=…>` it does not sit
 * inside — needed when the row lives in BottomSheet's sticky `footer` slot
 * (which renders outside the form) so the button still submits it natively.
 *
 * `submitVariant` covers destructive confirms (a Reject/Delete row wants the
 * affirmative half in `danger`), so those rows keep the shared Cancel-left /
 * affirmative-right order instead of hand-rolling their own.
 */
export default function ModalActions({
  onClose,
  submitLabel = 'Save',
  savingLabel = 'Saving…',
  submitVariant = 'primary',
  saving = false,
  submitDisabled = false,
  cancelLabel = 'Cancel',
  fullWidth = false,
  cancelVariant = fullWidth ? 'secondary' : 'ghost',
  size = fullWidth ? 'md' : 'sm',
  formId,
  className = '',
}) {
  const rowClass = fullWidth ? 'flex gap-2 pt-2' : 'flex justify-end gap-2 pt-2';
  const buttonClass = fullWidth ? 'flex-1' : '';
  return (
    <div className={`${rowClass} ${className}`}>
      <Button
        type="button"
        variant={cancelVariant}
        size={size}
        onClick={onClose}
        disabled={saving}
        className={buttonClass}
      >
        {cancelLabel}
      </Button>
      <Button
        type="submit"
        form={formId}
        variant={submitVariant}
        size={size}
        loading={saving}
        // `saving` is folded in explicitly: Button spreads its rest props
        // after computing `disabled`, so passing `disabled={false}` alongside
        // `loading` would hand a saving form a live submit button.
        disabled={submitDisabled || saving}
        className={buttonClass}
      >
        {/* Wrapped so Button's loading branch renders this label rather than
            substituting its own generic "Saving…" for a bare string child. */}
        {saving ? <span>{savingLabel}</span> : submitLabel}
      </Button>
    </div>
  );
}
