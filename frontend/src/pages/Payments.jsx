import { motion } from 'framer-motion';
import { DollarSign, TrendingUp, TrendingDown, ArrowDownRight, ArrowUpRight } from 'lucide-react';
import { getBalance } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';

const typeIcons = {
  hourly: { icon: TrendingUp, color: 'text-blue-400' },
  project_bonus: { icon: TrendingUp, color: 'text-green-400' },
  milestone_bonus: { icon: TrendingUp, color: 'text-emerald-400' },
  materials_reimbursement: { icon: ArrowUpRight, color: 'text-cyan-400' },
  payout: { icon: ArrowDownRight, color: 'text-red-400' },
  adjustment: { icon: DollarSign, color: 'text-yellow-400' },
};

const typeLabels = {
  hourly: 'Hourly',
  project_bonus: 'Project Bonus',
  milestone_bonus: 'Milestone Bonus',
  materials_reimbursement: 'Reimbursement',
  payout: 'Payout',
  adjustment: 'Adjustment',
};

export default function Payments() {
  const { data, loading } = useApi(getBalance);

  if (loading) return <Loader />;
  if (!data) return null;

  const { balance, breakdown, recent_transactions } = data;

  return (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-bold">Payments</h1>

      {/* Balance Card */}
      <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
        <Card className="text-center py-6">
          <div className="text-sm text-forge-text-dim mb-1">Current Balance</div>
          <div className={`font-heading text-5xl font-bold ${balance >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${balance?.toFixed(2)}
          </div>
        </Card>
      </motion.div>

      {/* Breakdown */}
      {breakdown && Object.keys(breakdown).length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3">Breakdown</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries(breakdown).map(([type, amount]) => {
              const { icon: Icon, color } = typeIcons[type] || typeIcons.adjustment;
              return (
                <Card key={type}>
                  <div className="flex items-center gap-2 mb-1">
                    <Icon size={14} className={color} />
                    <span className="text-xs text-forge-text-dim">{typeLabels[type] || type}</span>
                  </div>
                  <div className={`font-heading font-bold ${amount >= 0 ? 'text-forge-text' : 'text-red-400'}`}>
                    ${amount?.toFixed(2)}
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* Recent Transactions */}
      {recent_transactions?.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3">Recent Transactions</h2>
          <div className="space-y-2">
            {recent_transactions.map((tx) => {
              const { icon: Icon, color } = typeIcons[tx.entry_type] || typeIcons.adjustment;
              const isPositive = parseFloat(tx.amount) >= 0;
              return (
                <Card key={tx.id} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-full bg-forge-muted flex items-center justify-center ${color}`}>
                      <Icon size={16} />
                    </div>
                    <div>
                      <div className="text-sm font-medium">{typeLabels[tx.entry_type] || tx.entry_type}</div>
                      <div className="text-xs text-forge-text-dim truncate max-w-48">{tx.description}</div>
                    </div>
                  </div>
                  <div className={`font-heading font-bold text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                    {isPositive ? '+' : ''}${parseFloat(tx.amount).toFixed(2)}
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
