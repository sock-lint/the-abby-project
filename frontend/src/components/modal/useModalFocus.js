import { useLayoutEffect, useRef, useState } from 'react';

const FOCUSABLE_SELECTOR =
  'a[href], area[href], button, input, select, textarea, summary, [tabindex], [contenteditable="true"]';

// One keyboard owner for every modal layer. A portal can be mounted inside
// another sheet, so independent document listeners would both handle Escape.
const modals = [];
let nextOrder = 0;

function topModal() {
  return modals.reduce((top, modal) => (
    modal.node.isConnected && (!top || modal.order > top.order) ? modal : top
  ), null);
}

function isVisible(node) {
  for (let current = node; current; current = current.parentElement) {
    if (current.hidden || current.inert || current.getAttribute('aria-hidden') === 'true') return false;
    const style = window.getComputedStyle(current);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
  }
  return true;
}

function focusableElements(modal) {
  return Array.from(modal.node.querySelectorAll(FOCUSABLE_SELECTOR)).filter((node) => (
    node.tabIndex >= 0 && !node.matches(':disabled') && isVisible(node)
  ));
}

function focusInitial(modal) {
  const preferred = modal.initialFocusRef?.current;
  const target = preferred && modal.node.contains(preferred) && isVisible(preferred)
    ? preferred
    : focusableElements(modal)[0] || modal.node;
  target.focus();
}

function handleKeyDown(event) {
  const modal = topModal();
  if (!modal) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();
    modal.onEscapeRef.current?.();
    return;
  }
  if (event.key !== 'Tab') return;

  const focusable = focusableElements(modal);
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const current = document.activeElement;
  if (!first) {
    event.preventDefault();
    modal.node.focus();
  } else if (!modal.node.contains(current) || current === modal.node) {
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
  } else if (event.shiftKey && current === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && current === last) {
    event.preventDefault();
    first.focus();
  }
}

function handleFocusIn(event) {
  const modal = topModal();
  if (modal && !modal.node.contains(event.target)) focusInitial(modal);
}

/**
 * Trap focus and Escape in the most recently opened modal, then return focus
 * to its opener. The order is allocated during the first render so a child
 * modal stays on top even though React runs child layout effects first.
 * surfaceKey re-registers a sheet when its mobile/desktop DOM surface changes.
 */
export default function useModalFocus({ dialogRef, initialFocusRef, onEscape, surfaceKey }) {
  const [identity] = useState(() => ({
    order: ++nextOrder,
    opener: document.activeElement,
  }));
  const onEscapeRef = useRef(onEscape);
  useLayoutEffect(() => { onEscapeRef.current = onEscape; }, [onEscape]);

  useLayoutEffect(() => {
    const node = dialogRef.current;
    if (!node) return undefined;
    const modal = { ...identity, node, initialFocusRef, onEscapeRef };
    if (modals.length === 0) {
      document.addEventListener('keydown', handleKeyDown, true);
      document.addEventListener('focusin', handleFocusIn, true);
    }
    modals.push(modal);
    if (topModal() === modal) focusInitial(modal);

    return () => {
      const wasTop = topModal() === modal;
      modals.splice(modals.indexOf(modal), 1);
      // When an outer sheet and its child close in the same commit, the
      // child's opener is about to disappear too. Restore the outer opener.
      for (const remaining of modals) {
        if (node.contains(remaining.opener)) remaining.opener = modal.opener;
      }
      if (modals.length === 0) {
        document.removeEventListener('keydown', handleKeyDown, true);
        document.removeEventListener('focusin', handleFocusIn, true);
      }
      if (!wasTop) return;
      const next = topModal();
      if (modal.opener?.isConnected && isVisible(modal.opener)
        && (!next || next.node.contains(modal.opener))) {
        modal.opener.focus();
      } else if (next) {
        focusInitial(next);
      }
    };
  }, [dialogRef, identity, initialFocusRef, surfaceKey]);
}
