import { motion } from 'framer-motion';
import { ArrowRightLeft } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { CoinIcon } from '../../components/icons/JournalIcons';

export default function CoinBalanceCard({ coinBalance, isParent, onOpenExchange }) {
  return (
    <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
      <ParchmentCard flourish tone="bright" className="text-center py-7">
        <div className="font-script text-sheikah-teal-deep text-sm uppercase tracking-widest flex items-center justify-center gap-1.5">
          <CoinIcon size={16} className="text-gold-leaf" /> coin balance
        </div>
        <div className="font-display font-semibold text-5xl md:text-6xl text-gold-leaf tabular-nums mt-1">
          {coinBalance}
        </div>
        {!isParent && (
          <button
            type="button"
            onClick={onOpenExchange}
            className="mt-4 inline-flex items-center gap-1.5 bg-sheikah-teal/20 hover:bg-sheikah-teal/30 text-sheikah-teal-deep font-body font-medium px-4 py-2 rounded-lg border border-sheikah-teal/50 transition-colors"
          >
            <ArrowRightLeft size={14} /> Exchange money for coins
          </button>
        )}
      </ParchmentCard>
    </motion.div>
  );
}
