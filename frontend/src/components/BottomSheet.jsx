import { motion } from 'framer-motion';
import { X } from 'lucide-react';

export default function BottomSheet({ title, onClose, disabled, children }) {
  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={disabled ? undefined : onClose}
        className="fixed inset-0 bg-black/60 z-40"
      />
      <motion.div
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        exit={{ y: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className="fixed bottom-0 left-0 right-0 bg-forge-card border-t border-forge-border rounded-t-2xl z-50 pb-[env(safe-area-inset-bottom)] max-h-[90vh] overflow-y-auto md:left-1/2 md:right-auto md:bottom-auto md:top-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-full md:max-w-md md:rounded-2xl md:border"
      >
        <div className="flex justify-center pt-2 md:hidden">
          <div className="w-10 h-1 rounded-full bg-forge-muted" />
        </div>
        <div className="flex items-center justify-between px-4 pt-3 pb-2">
          <h2 className="font-heading text-lg font-bold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={disabled}
            aria-label="Close"
            className="text-forge-text-dim hover:text-forge-text min-h-10 min-w-10 flex items-center justify-center rounded-lg"
          >
            <X size={20} />
          </button>
        </div>
        <div className="px-4 pb-4 space-y-3">
          {children}
        </div>
      </motion.div>
    </>
  );
}
