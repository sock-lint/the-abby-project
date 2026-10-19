import ParchmentCard from '../../components/journal/ParchmentCard';
import SectionHeader from '../../components/SectionHeader';
import { expeditionBudgetLabel } from './progressionLabScenario';

const number = (value) => Number.isFinite(value) ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value) : 'Unavailable';
const rows = [
  ['requested_trips', 'Trips requested by the routine'], ['eligible_trips', 'Trips with an available mount'],
  ['launched_trips', 'Trips launched'], ['prevented_trips', 'Trips prevented by launch limit'],
  ['unavailable_mount_trips', 'Requests without an available mount'],
  ['slots_requested', 'Nominal item slots on launched trips'], ['slots_promised', 'New item slots promised'],
  ['slots_withheld_by_budget', 'Item slots withheld by limit'], ['slots_unfilled_by_pool', 'Slots with no eligible item'],
  ['claimed_items', 'Item units claimed'], ['pending_items', 'Item units awaiting claim'],
  ['grandfathered_claimed_items', 'Claimed units from older promises'], ['grandfathered_pending_items', 'Pending units from older promises'],
  ['zero_item_trips', 'Trips promising zero items'], ['zero_coin_trips', 'Trips promising zero direct Coins'],
  ['empty_trips', 'Trips promising no Coins or items'],
  ['launch_limited_days', 'Days when a launch was prevented'], ['item_limited_days', 'Days when an item slot was withheld'],
  ['launch_saturated_days', 'Days when launch allowance was fully used'], ['item_saturated_days', 'Days when item allowance was fully used'],
];

export default function ProgressionExpeditionBudgetReport({ budget, baseline }) {
  if (!budget) return null;
  const launches = budget.summary.launched_trips?.mean;
  const share = (key) => launches > 0 ? `${number(100 * budget.summary[key]?.mean / launches)}%` : 'Unavailable';
  return <ParchmentCard as="section" aria-label="Expedition budget forecast" className="space-y-3">
    <SectionHeader as="h3" title="Expedition limits and reward quality">{expeditionBudgetLabel(budget)}. Totals are per child over the whole forecast.</SectionHeader>
    {baseline && <p className="text-caption text-ink-secondary">Comparison limits: {expeditionBudgetLabel(baseline)}.</p>}
    <p className="text-body text-ink-secondary">Zero-direct-Coin trips: {share('zero_coin_trips')}. Completely empty trips: {share('empty_trips')}. Shares use aggregate counts across all children; they are unavailable when no trips launch.</p>
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Expedition limits, horizontally scrollable"><table className="w-full text-body text-left"><caption className="sr-only">Expedition trip and item totals per simulated child</caption><thead><tr><th className="p-2">Measure</th>{['10th percentile', 'Median', '90th percentile', 'Mean', ...(baseline ? ['Comparison median'] : [])].map((label) => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>{rows.filter(([key]) => budget.summary[key]).map(([key, label]) => <tr key={key} className="border-t border-ink-page-shadow"><th scope="row" className="p-2">{label}</th>{['p10', 'p50', 'p90', 'mean'].map((quantile) => <td key={quantile} className="p-2">{number(budget.summary[key]?.[quantile])}</td>)}{baseline && <td className="p-2">{number(baseline.summary[key]?.p50)}</td>}</tr>)}</tbody></table></div>
    <p className="text-caption text-ink-secondary">Nominal slots count launched trips only and equal new promises + slots withheld by the item limit + slots with no eligible item. New promises equal claimed + pending units after excluding older promises. Use means to reconcile totals; independent medians may describe different children. A zero-direct-Coin trip can still contain items or Coin pouches.</p>
    <p className="text-body text-ink-secondary">Finite targets with unlimited expeditions under the same Coin rules: {number(budget.unlimited_finite_total)}. Targets losing their modeled acquisition path under these limits: {number(budget.unavailable_finite_total)}. Removing access does not create additional content runway.</p>
    {Object.values(budget.removed_finite_targets ?? {}).some((value) => value > 0) && <p className="text-caption text-ink-secondary">Unavailable targets by kind: {Object.entries(budget.removed_finite_targets).map(([key, value]) => `${key}: ${number(value)}`).join(' · ')}.</p>}
    <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Expedition limit assumptions</summary><ul className="list-disc pl-5 space-y-2 text-caption text-ink-secondary">{budget.assumptions.map((entry) => <li key={entry}>{entry}</li>)}</ul></details>
  </ParchmentCard>;
}
