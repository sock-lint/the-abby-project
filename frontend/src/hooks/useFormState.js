import { useState, useCallback } from 'react';

/**
 * Bundles the form + saving + error state every CRUD modal needs.
 *
 * Returns:
 *   form     — current form values
 *   set      — patch(partialOrFn): merge a partial object or functional updater
 *              into the form state
 *   setForm  — raw setter, for wholesale replacement
 *   saving   — in-flight flag while submitting
 *   setSaving
 *   error    — error message (or null)
 *   setError
 *   reset    — restore the initial values
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

  const reset = useCallback(() => setForm(initial), [initial]);

  return { form, set, setForm, saving, setSaving, error, setError, reset };
}
