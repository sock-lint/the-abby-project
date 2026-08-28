import { useEffect } from 'react';

// Body scroll lock for the "Sheikah Stamp" modal family.
//
// Without this, a touch drag that starts on the backdrop — or anywhere on a
// short sheet whose own content doesn't scroll — scrolls the page underneath,
// so the sheet closes onto a page that has silently moved. Worse, in the
// installed Android PWA that same drag chains into browser pull-to-refresh at
// scrollTop 0, reloading the SPA and discarding the half-typed form the
// sheet's dirty guard exists to protect.
//
// `overscroll-behavior: contain` on the scrolling elements is what stops the
// pull-to-refresh chain; `overflow: hidden` stops the page moving at all.
//
// Reference-counted because modals stack: a ConfirmDialog opening over a
// BottomSheet mounts a second backdrop, and the inner one unmounting must not
// release the outer one's lock.
let lockCount = 0;
let restore = null;

function snapshot(el) {
  return {
    el,
    overflow: el.style.overflow,
    overscrollBehaviorY: el.style.overscrollBehaviorY,
  };
}

export function lockBodyScroll() {
  if (typeof document === 'undefined' || !document.body) return;
  lockCount += 1;
  if (lockCount > 1) return;
  restore = [document.documentElement, document.body].map(snapshot);
  for (const { el } of restore) {
    el.style.overflow = 'hidden';
    el.style.overscrollBehaviorY = 'contain';
  }
}

export function unlockBodyScroll() {
  if (lockCount === 0) return;
  lockCount -= 1;
  if (lockCount > 0) return;
  for (const entry of restore || []) {
    entry.el.style.overflow = entry.overflow;
    entry.el.style.overscrollBehaviorY = entry.overscrollBehaviorY;
  }
  restore = null;
}

/**
 * useBodyScrollLock(active) — hold the lock for as long as the component is
 * mounted. Mounted by ModalBackdrop, so every surface in the modal family
 * (BottomSheet, ConfirmDialog) gets it without a per-call-site opt-in.
 */
export function useBodyScrollLock(active = true) {
  useEffect(() => {
    if (!active) return undefined;
    lockBodyScroll();
    return unlockBodyScroll;
  }, [active]);
}
