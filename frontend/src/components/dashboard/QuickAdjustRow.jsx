import { useNavigate } from 'react-router-dom';
import { Wallet, CircleDollarSign } from 'lucide-react';

function AdjustButton({ icon, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-ink-page border border-ink-page-shadow hover:bg-ink-page-rune-glow transition-colors font-body text-sm text-ink-primary"
    >
      <span className="text-sheikah-teal-deep">{icon}</span>
      {label}
    </button>
  );
}

/**
 * QuickAdjustRow — parent shortcuts to the two manual ledger adjustments.
 * These live on /manage today; this is a fast door.
 */
export default function QuickAdjustRow() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-wrap gap-2">
      <AdjustButton
        icon={<Wallet size={16} />}
        label="Adjust coins"
        onClick={() => navigate('/manage?tab=coins')}
      />
      <AdjustButton
        icon={<CircleDollarSign size={16} />}
        label="Adjust payment"
        onClick={() => navigate('/manage?tab=payments')}
      />
    </div>
  );
}
