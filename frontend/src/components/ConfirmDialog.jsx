import { motion, AnimatePresence } from 'framer-motion';

export default function ConfirmDialog({ title, message, confirmLabel = 'Delete', onConfirm, onCancel }) {
  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      >
        <div className="absolute inset-0 bg-black/60" onClick={onCancel} />
        <motion.div
          className="relative bg-forge-card border border-forge-border rounded-2xl p-5 max-w-sm w-full mx-4"
          initial={{ scale: 0.9 }} animate={{ scale: 1 }}
        >
          <h3 className="font-heading font-bold mb-2">{title}</h3>
          <p className="text-sm text-forge-text-dim mb-4">{message}</p>
          <div className="flex justify-end gap-2">
            <button onClick={onCancel} className="px-4 py-2 text-sm text-forge-text-dim hover:text-forge-text">Cancel</button>
            <button
              onClick={onConfirm}
              className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-300 text-sm font-semibold rounded-lg border border-red-500/30"
            >
              {confirmLabel}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
