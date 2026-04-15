import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Package, X } from 'lucide-react';
import { useDropToasts } from '../hooks/useDropToasts';
import RpgSprite from './rpg/RpgSprite';

const RARITY_BG = {
  common: 'bg-gray-600 border-gray-400',
  uncommon: 'bg-green-700 border-green-400',
  rare: 'bg-blue-700 border-blue-400',
  epic: 'bg-purple-700 border-purple-400',
  legendary: 'bg-amber-700 border-amber-400',
};

function ToastItem({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 6000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <motion.div
      layout
      initial={{ x: 300, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 300, opacity: 0 }}
      className={`flex items-center gap-3 rounded-lg border px-3 py-2 shadow-lg ${RARITY_BG[toast.item_rarity] || RARITY_BG.common}`}
    >
      <Package size={18} className="text-white shrink-0" />
      <RpgSprite
        spriteKey={toast.item_sprite_key}
        icon={toast.item_icon}
        size={32}
        alt={toast.item_name}
      />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-medium text-white">
          {toast.was_salvaged ? 'Salvaged' : 'You got'}: {toast.item_name}
        </div>
        <div className="text-[10px] text-white/70 capitalize">{toast.item_rarity}</div>
      </div>
      <button onClick={() => onDismiss(toast.id)} className="text-white/70 hover:text-white shrink-0">
        <X size={14} />
      </button>
    </motion.div>
  );
}

export default function DropToastStack() {
  const { toasts, dismiss } = useDropToasts();

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none">
      <AnimatePresence>
        {toasts.map(t => (
          <div key={t.id} className="pointer-events-auto">
            <ToastItem toast={t} onDismiss={dismiss} />
          </div>
        ))}
      </AnimatePresence>
    </div>
  );
}
