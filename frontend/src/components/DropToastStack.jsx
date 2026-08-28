import { TOAST_DURATION_LONG } from '../constants/timing';
import { useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Package, X } from 'lucide-react';
import { useDropToasts } from '../hooks/useDropToasts';
import IconButton from './IconButton';
import RpgSprite from './rpg/RpgSprite';
import RareDropReveal from './RareDropReveal';
import { RARE_TIERS } from './rareDropTiers';
import { swipeToDismiss } from './toastSwipe';
import { RARITY_SOLID_COLORS } from '../constants/colors';
// Shared with the Lorebook first-encounter sheet — both are pulse-driven
// reveals that must wait for an open form before taking over the screen.
import { useDeferUntilDialogsClose } from './lorebook/dialogPresence';

function ToastItem({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), TOAST_DURATION_LONG);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <motion.div
      layout
      initial={{ x: 300, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 300, opacity: 0 }}
      {...swipeToDismiss(() => onDismiss(toast.id))}
      className={`flex items-center gap-3 rounded-lg border border-white/25 px-3 py-2 shadow-lg ${RARITY_SOLID_COLORS[toast.item_rarity] || RARITY_SOLID_COLORS.common}`}
    >
      <Package size={18} className="text-white shrink-0" />
      <RpgSprite
        spriteKey={toast.item_sprite_key}
        icon={toast.item_icon}
        size={32}
        alt={toast.item_name}
      />
      <div className="flex-1 min-w-0">
        <div className="text-caption font-medium text-white">
          {toast.was_salvaged ? 'Salvaged' : 'You got'}: {toast.item_name}
        </div>
        <div className="text-micro text-white/70 capitalize">{toast.item_rarity}</div>
      </div>
      <IconButton
        onClick={() => onDismiss(toast.id)}
        variant="ghost"
        size="sm"
        aria-label="Dismiss notification"
        className="text-white/70 hover:text-white shrink-0"
      >
        <X size={14} />
      </IconButton>
    </motion.div>
  );
}

export default function DropToastStack({ inline = false }) {
  const { toasts, dismiss } = useDropToasts();

  const { commonToasts, rareQueue } = useMemo(() => {
    const c = [];
    const r = [];
    for (const t of toasts) {
      if (RARE_TIERS.has(t.item_rarity)) r.push(t);
      else c.push(t);
    }
    return { commonToasts: c, rareQueue: r };
  }, [toasts]);

  const activeReveal = rareQueue[0] || null;
  // Hold the full-screen reveal back while a sheet or dialog is open — it
  // would otherwise land on top of a half-filled form. The drop stays queued.
  const revealReady = useDeferUntilDialogsClose(activeReveal);

  const items = (
    <AnimatePresence>
      {commonToasts.map(t => (
        <div key={t.id} className="pointer-events-auto">
          <ToastItem toast={t} onDismiss={dismiss} />
        </div>
      ))}
    </AnimatePresence>
  );

  return (
    <>
      {inline ? items : (
        <div className="fixed top-4 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none" aria-live="polite" aria-atomic="false">
          {items}
        </div>
      )}
      {activeReveal && revealReady && (
        <RareDropReveal drop={activeReveal} onDismiss={dismiss} />
      )}
    </>
  );
}
