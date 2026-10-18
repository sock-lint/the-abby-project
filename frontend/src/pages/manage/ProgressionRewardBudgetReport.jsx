import SectionHeader from '../../components/SectionHeader';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { rewardBudgetLabel } from './progressionLabScenario';

const number = (value) => Number.isFinite(value) ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value) : 'Unavailable';
const metricRows = [
  ['raw_coins', 'Coins requested from budgeted sources'],
  ['awarded_coins', 'Coins awarded from budgeted sources'],
  ['omitted_coins', 'Coins omitted by the budget'],
  ['capped_days', 'Days when the budget reduced a reward'],
];
const sourceLabels = { expeditions: 'Direct expedition Coins', expeditions_salvage: 'Expedition duplicate salvage', coin_pouches: 'All Coin pouches' };

export default function ProgressionRewardBudgetReport({ budget, baseline }) {
  if (!budget) return null;
  return <ParchmentCard as="section" aria-label="Reward budget forecast" className="space-y-3">
    <SectionHeader as="h3" title="Expedition and Coin-pouch budget results">{rewardBudgetLabel(budget)}</SectionHeader>
    {baseline && <p className="text-body text-ink-secondary">Comparison budget: {rewardBudgetLabel(baseline)}.</p>}
    <p className="text-body text-ink-secondary">Each simulated child has their own daily allowance shared across direct expedition Coins, expedition duplicate salvage and all Coin pouches. Other Coin sources remain outside this allowance. Excess Coins are omitted, not deferred; live rewards stay unchanged.</p>
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Reward budget totals, horizontally scrollable">
      <table className="w-full text-body text-left"><caption className="sr-only">Reward budget totals across simulated journeys</caption>
        <thead><tr><th className="p-2">Measure</th><th className="p-2">10th percentile</th><th className="p-2">Median</th><th className="p-2">90th percentile</th><th className="p-2">Mean</th>{baseline && <th className="p-2">Comparison median</th>}</tr></thead>
        <tbody>{metricRows.map(([key, label]) => <tr key={key} className="border-t border-ink-page-shadow"><th scope="row" className="p-2 font-semibold">{label}</th>{['p10', 'p50', 'p90', 'mean'].map((quantile) => <td key={quantile} className="p-2 whitespace-nowrap">{number(budget.summary[key]?.[quantile])}</td>)}{baseline && <td className="p-2 whitespace-nowrap">{number(baseline.summary[key]?.p50)}</td>}</tr>)}</tbody>
      </table>
    </div>
    <p className="text-caption text-ink-secondary">Requested Coins come from this journey’s reward rolls before its budget is applied. They are not the total from a separate uncapped journey: budget changes can affect later unlocks and rolls. Separate medians can describe different journeys; use the means or individual receipts to reconcile totals.</p>
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Reward budget sources, horizontally scrollable">
      <table className="w-full text-body text-left"><caption className="sr-only">Reward budget source totals, mean per simulated child</caption>
        <thead><tr><th className="p-2">Source</th><th className="p-2">Requested Coins</th><th className="p-2">Awarded Coins</th><th className="p-2">Omitted Coins</th>{baseline && <th className="p-2">Comparison awarded Coins</th>}</tr></thead>
        <tbody>{budget.sources.map((row) => <tr key={row.source} className="border-t border-ink-page-shadow"><th scope="row" className="p-2 font-semibold">{sourceLabels[row.source] ?? row.source}</th>{['raw_coins', 'awarded_coins', 'omitted_coins'].map((key) => <td key={key} className="p-2 whitespace-nowrap">{number(row[key]?.mean)}</td>)}{baseline && <td className="p-2 whitespace-nowrap">{number(baseline.sources.find((source) => source.source === row.source)?.awarded_coins?.mean)}</td>}</tr>)}</tbody>
      </table>
    </div>
    <details><summary className="min-h-11 py-3 cursor-pointer font-semibold text-ink-primary">Reward budget model assumptions</summary><ul className="list-disc pl-5 space-y-2 text-body text-ink-secondary">{budget.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></details>
  </ParchmentCard>;
}
