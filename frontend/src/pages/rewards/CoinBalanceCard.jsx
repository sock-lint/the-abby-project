import { motion } from 'framer-motion';
import { ArrowRightLeft, Coins } from 'lucide-react';
import Card from '../../components/Card';

export default function CoinBalanceCard({ coinBalance, isParent, onOpenExchange }) {
  return (
    <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
      <Card className="text-center py-5">
        <div className="text-xs text-forge-text-dim mb-1 flex items-center justify-center gap-1">
          <Coins size={14} /> Coin Balance
        </div>
        <div className="font-heading text-4xl font-bold text-amber-highlight">{coinBalance}</div>
        {!isParent && (
          <button
            onClick={onOpenExchange}
            className="mt-3 inline-flex items-center gap-1.5 bg-amber-primary/20 hover:bg-amber-primary/30 text-amber-highlight text-xs font-semibold px-4 py-2 rounded-lg border border-amber-primary/30"
          >
            <ArrowRightLeft size={14} /> Exchange Money for Coins
          </button>
        )}
      </Card>
    </motion.div>
  );
}
