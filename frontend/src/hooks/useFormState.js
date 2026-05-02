import { useState, useCallback } from 'react';

/**
 * Bundles the form + saving + error state every CRUD modal needs.
 *
 * Returns:
 *   form        — current form values
 *   set         — patch(partialOrFn): merge a partial object or functional updater
 *                 into the form state
 *   setForm     — raw setter, for wholesale replacement
 *   onField     — `onField('key')` returns a `(e) => set({ key: e.target.value })`
 *                 handler. The factory exists in every form modal — own it here.
 *   saving      — in-flight flag while submitting
 *   setSaving
 *   error       — error message (or null)
 *   setError
 *   reset       — restore the initial values
 *   submit(fn)  — wrap an async submit in the standard
 *                 preventDefault → setSaving(true) → setError(null) →
 *                 try/catch → finally setSaving(false) shape. Use as
 *                 `<form onSubmit={submit(async (form) => …)}>`. The
 *                 handler receives the current form values.
 */
export function useFormState(initial) {
  const [form, setForm] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const set = useCallback((patch) => {
    setForm((f) => ({
      ...f,
      ...(typeof patch === 'function' ? patch(f) : patch),
    }));
  }, []);

  const onField = useCallback(
    (key) => (e) => set({ [key]: e?.target ? e.target.value : e }),
    [set],
  );

  const reset = useCallback(() => setForm(initial), [initial]);

  const submit = useCallback(
    (handler) => async (event) => {
      if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
      }
      setSaving(true);
      setError(null);
      try {
        await handler(form);
      } catch (err) {
        setError(err?.message || 'Something went wrong');
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [form],
  );

  return {
    form, set, setForm, onField,
    saving, setSaving,
    error, setError,
    reset, submit,
  };
}
