import { createContext, useContext } from 'react';

export const SuccessToastContext = createContext(null);

export function useSuccessToast() {
  const ctx = useContext(SuccessToastContext);
  if (!ctx) throw new Error('useSuccessToast must be inside SuccessToastProvider');
  return ctx;
}
