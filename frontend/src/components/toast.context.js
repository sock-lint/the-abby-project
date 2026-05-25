import { createContext, useContext } from 'react';

export const ToastContext = createContext(null);

export function useToastManager() {
  return useContext(ToastContext);
}
