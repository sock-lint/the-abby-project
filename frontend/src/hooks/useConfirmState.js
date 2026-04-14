import { useCallback, useState } from 'react';

/**
 * Packages the open/close state for a <ConfirmDialog>. Pass the returned
 * ``confirmState`` to ConfirmDialog when rendering (null = hidden).
 *
 * Usage:
 *   const { confirmState, askConfirm, closeConfirm } = useConfirmState();
 *   askConfirm({ title, message, onConfirm, confirmLabel });
 *
 *   {confirmState && (
 *     <ConfirmDialog
 *       title={confirmState.title}
 *       message={confirmState.message}
 *       confirmLabel={confirmState.confirmLabel}
 *       onConfirm={async () => {
 *         const fn = confirmState.onConfirm;
 *         closeConfirm();
 *         await fn();
 *       }}
 *       onCancel={closeConfirm}
 *     />
 *   )}
 */
export function useConfirmState() {
  const [confirmState, setConfirmState] = useState(null);

  const askConfirm = useCallback((opts) => setConfirmState(opts), []);
  const closeConfirm = useCallback(() => setConfirmState(null), []);

  return { confirmState, askConfirm, closeConfirm };
}
