import { useNavigate } from 'react-router-dom';
import { Wallet, CircleDollarSign } from 'lucide-react';

function AdjustButton({ icon, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-ink-page border border-ink-page-shadow hover:bg-ink-page-rune-glow transition-colors font-body text-body text-ink-primary"
    >
      <span className="text-sheikah-teal-deep">{icon}</span>
      {label}
    </button>
  );
}

/**
 * QuickAdjustRow — parent shortcuts to the two manual ledger adjustments.
 * Both live on Treasury (Bazaar holds the coin adjuster, Coffers the balance
 * adjuster); ?adjust=1 opens the sheet on arrival.
 */
export default function QuickAdjustRow() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-wrap gap-2">
      <AdjustButton
        icon={<Wallet size={16} />}
        label="Adjust coins"
        onClick={() => navigate('/treasury?tab=bazaar&adjust=1')}
      />
      <AdjustButton
        icon={<CircleDollarSign size={16} />}
        label="Adjust payment"
        onClick={() => navigate('/treasury?tab=coffers&adjust=1')}
      />
    </div>
  );
}
