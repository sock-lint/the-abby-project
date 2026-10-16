import { TOAST_DURATION_LONG } from '../constants/timing';
import { useEffect, useMemo } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Package } from 'lucide-react';
import { useDropToasts } from '../hooks/useDropToasts';
import NotificationToast from './NotificationToast';
import RpgSprite from './rpg/RpgSprite';
import RareDropReveal from './RareDropReveal';
import { RARE_TIERS } from './rareDropTiers';
// Shared with the Lorebook first-encounter sheet — both are pulse-driven
// reveals that must wait for an open form before taking over the screen.
import { useDeferUntilDialogsClose } from './lorebook/dialogPresence';

function ToastItem({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), TOAST_DURATION_LONG);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <NotificationToast
      rarity={toast.item_rarity}
      onDismiss={() => onDismiss(toast.id)}
    >
      <Package size={18} className="text-current shrink-0" />
      <RpgSprite
        spriteKey={toast.item_sprite_key}
        icon={toast.item_icon}
        size={32}
        alt={toast.item_name}
      />
      <div className="flex-1 min-w-0">
        <div className="text-caption font-medium text-current">
          {toast.was_salvaged ? 'Salvaged' : 'You got'}: {toast.item_name}
        </div>
        <div className="text-caption text-current capitalize">{toast.item_rarity}</div>
      </div>
    </NotificationToast>
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
