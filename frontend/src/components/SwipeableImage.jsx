import { motion } from 'framer-motion';

// Travel required before a fling counts. Vertical needs more than horizontal
// so a sloppy sideways swipe doesn't close the viewer by accident.
const SWIPE_NEXT_PX = 70;
const SWIPE_CLOSE_PX = 110;

/**
 * SwipeableImage — the photo inside a full-screen lightbox, with the gestures
 * every phone user brings from their camera roll: fling sideways to move
 * through the set, fling down to dismiss. Chevron buttons stay for desktop
 * (and as the tap fallback); this only adds the touch affordances.
 *
 * Shared by the Sketchbook lightbox (pages/Portfolio.jsx) and the homework
 * ProofGallery — the second consumer is what promoted it to components/.
 */
export default function SwipeableImage({
  src, alt, className = '', onPrev, onNext, onClose,
}) {
  return (
    <motion.img
      // Keying on src makes each photo animate in rather than cross-fading
      // in place, so the advance reads as physical movement.
      key={src}
      src={src}
      alt={alt}
      className={className}
      drag
      dragConstraints={{ left: 0, right: 0, top: 0, bottom: 0 }}
      dragElastic={0.4}
      dragMomentum={false}
      onClick={(e) => e.stopPropagation()}
      onDragEnd={(_event, info) => {
        const { x, y } = info.offset;
        if (y > SWIPE_CLOSE_PX && Math.abs(y) > Math.abs(x)) {
          onClose?.();
          return;
        }
        if (x <= -SWIPE_NEXT_PX) onNext?.();
        else if (x >= SWIPE_NEXT_PX) onPrev?.();
      }}
    />
  );
}
