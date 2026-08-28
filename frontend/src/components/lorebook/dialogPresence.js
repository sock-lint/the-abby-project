import { useEffect, useState } from 'react';

// Any modal surface in the app: BottomSheet renders role="dialog",
// ConfirmDialog and the celebration reveals render role="alertdialog".
const DIALOG_SELECTOR = '[role="dialog"], [role="alertdialog"]';

function aDialogIsOpen() {
  return typeof document !== 'undefined'
    && document.querySelector(DIALOG_SELECTOR) !== null;
}

/**
 * Gate for the two pulse-driven reveals — the Lorebook first-encounter sheet
 * and the rare-drop reveal. Both fire off the 30s heartbeat, right after the
 * actions kids do mid-flow (habit tap, chore complete, clock-in), so without
 * a gate they stack a second z-50 portal over a form that is already open,
 * steal its focus and dismiss the phone keyboard mid-word.
 *
 * Returns true once `pending` is truthy AND nothing else is on screen. The
 * clearance latches, so the reveal's own dialog doesn't immediately re-close
 * it; it resets when `pending` goes falsy (the reveal was consumed).
 *
 * Shared by ../DropToastStack and ./FirstEncounterSheet.
 */
export function useDeferUntilDialogsClose(pending) {
  const [clear, setClear] = useState(false);

  useEffect(() => {
    if (!pending) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resetting the latch once the reveal is consumed
      setClear(false);
      return undefined;
    }
    if (clear) return undefined;
    if (!aDialogIsOpen()) {
      setClear(true);
      return undefined;
    }
    // Something is open — watch the portal root until it goes away.
    const observer = new MutationObserver(() => {
      if (!aDialogIsOpen()) setClear(true);
    });
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [pending, clear]);

  return Boolean(pending) && clear;
}
