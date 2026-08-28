// Horizontal travel before a toast is flung away.
const SWIPE_DISMISS_PX = 80;

/**
 * swipeToDismiss — shared drag props for the six toast stacks mounted in
 * JournalShell. They already animate in and out along x, so a fling reuses
 * the existing exit animation.
 *
 * drag="x" makes framer stamp `touch-action: pan-y`, so vertical page
 * scrolling through a toast stays native — the reason the sheet's drag had
 * to be scoped to its handle but this one is safe on the whole card.
 */
export function swipeToDismiss(onDismiss) {
  return {
    drag: 'x',
    dragConstraints: { left: 0, right: 0 },
    dragElastic: 0.6,
    dragMomentum: false,
    onDragEnd: (_event, info) => {
      if (Math.abs(info.offset.x) > SWIPE_DISMISS_PX) onDismiss();
    },
  };
}
