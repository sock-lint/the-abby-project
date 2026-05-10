import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import { TextField } from '../../components/form';
import { useFormState } from '../../hooks/useFormState';

/**
 * Shared password-reset sheet for both child and co-parent edit flows.
 *
 * Backend validation (Django's ``validate_password``) is the single source
 * of truth — we only do client-side "match" + "non-empty" checks. The
 * caller passes ``onSubmit(password)`` so the right endpoint
 * (``resetChildPassword`` or ``resetParentPassword``) is bound at the
 * call site.
 */
export default function ResetPasswordModal({ user, onSubmit, onClose, onDone }) {
  const { form, onField, saving, setSaving, error, setError } = useFormState({
    password: '',
    confirm: '',
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.password) {
      setError('Pick a new password.');
      return;
    }
    if (form.password !== form.confirm) {
      setError('Passwords do not match.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSubmit(form.password);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const label = user.display_name || user.username;

  return (
    <BottomSheet title={`Reset password for ${label}`} onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <p className="text-sm text-ink-whisper">
          Choose a new password. Their existing sessions will be signed out.
        </p>
        <TextField
          label="New password"
          type="password"
          value={form.password}
          onChange={onField('password')}
          required
          autoComplete="new-password"
        />
        <TextField
          label="Confirm new password"
          type="password"
          value={form.confirm}
          onChange={onField('confirm')}
          required
          autoComplete="new-password"
        />
        <div className="flex gap-2 justify-end pt-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Reset password'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}
