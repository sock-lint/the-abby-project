import { createContext, useContext } from 'react';

export const STORAGE_KEY = 'manage:test:checklist:v1';

// Created here so both ChecklistContext.jsx (the provider) and
// useChecklist (the hook) can import it without crossing the
// react-refresh/only-export-components rule that fires when a .jsx
// file exports both a component and a non-component value.
export const ChecklistCtx = createContext(null);

const NOOP_VALUE = {
  checked: new Set(),
  mark: () => {},
  toggle: () => {},
  clear: () => {},
  isChecked: () => false,
};

export function useChecklist() {
  return useContext(ChecklistCtx) || NOOP_VALUE;
}
