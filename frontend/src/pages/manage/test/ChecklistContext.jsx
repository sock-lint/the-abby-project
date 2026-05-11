import { useCallback, useMemo, useState } from 'react';
import { ChecklistCtx, STORAGE_KEY } from './useChecklist';

function loadChecks() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function saveChecks(set) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
  } catch {
    /* quota exceeded — silent */
  }
}

export function ChecklistProvider({ children }) {
  const [checked, setChecked] = useState(() => loadChecks());

  const mark = useCallback((id) => {
    if (!id) return;
    setChecked((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      saveChecks(next);
      return next;
    });
  }, []);

  const toggle = useCallback((id) => {
    if (!id) return;
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      saveChecks(next);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setChecked(new Set());
    saveChecks(new Set());
  }, []);

  const value = useMemo(() => ({
    checked,
    mark,
    toggle,
    clear,
    isChecked: (id) => checked.has(id),
  }), [checked, mark, toggle, clear]);

  return (
    <ChecklistCtx.Provider value={value}>
      {children}
    </ChecklistCtx.Provider>
  );
}
