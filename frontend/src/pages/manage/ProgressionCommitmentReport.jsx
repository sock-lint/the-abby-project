import ParchmentCard from '../../components/journal/ParchmentCard';
import SectionHeader from '../../components/SectionHeader';

const number = (value) => Number.isFinite(value) ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value) : 'Unavailable';
const rows = [
  ['committed_coins', 'New Coins committed'], ['expedition_direct_committed', 'Direct expedition Coins promised'],
  ['expedition_pouch_committed', 'Expedition pouch value promised'], ['expedition_salvage_reserved', 'Potential duplicate salvage reserved'],
  ['activity_pouch_committed', 'Random activity pouch value promised'], ['expedition_direct_paid', 'Direct expedition Coins paid'],
  ['expedition_salvage_paid', 'Duplicate salvage paid'], ['pouch_coins_paid', 'All pouch Coins paid'],
  ['outstanding_direct_coins', 'Direct Coins awaiting claim'], ['outstanding_pouch_coins', 'Pouch value awaiting claim or opening'],
  ['contingent_salvage_coins', 'Potential salvage awaiting claim'], ['released_salvage_reserve', 'Unused salvage reserve released'],
  ['zero_coin_launches', 'Trips promising zero direct Coins'], ['empty_expedition_launches', 'Trips with no Coins or items'],
  ['empty_item_slots', 'Unfilled expedition item slots'], ['activity_empty_drops', 'Activity drops with no eligible reward'],
];
export default function ProgressionCommitmentReport({ commitment }) {
  if (!commitment?.enabled) return null;
  return <ParchmentCard as="section" aria-label="Reward commitment forecast" className="space-y-3">
    <SectionHeader as="h3" title="Commitment prototype results">100 new Coins per child per day: 75 for expeditions, 25 for random activity pouches. This is not a daily payout cap or a live economy change.</SectionHeader>
    <p className="text-caption text-ink-secondary">Promises, actual wallet credits and potential salvage are separate. Authored challenge pouches and other Coin sources remain outside the allocation. Use means to reconcile totals; separate medians may represent different children.</p>
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Reward commitments, horizontally scrollable"><table className="w-full text-body text-left"><caption className="sr-only">Reward commitment totals per simulated child</caption><thead><tr><th className="p-2">Measure</th>{['10th percentile', 'Median', '90th percentile', 'Mean'].map((label) => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>{rows.map(([key, label]) => <tr key={key} className="border-t border-ink-page-shadow"><th scope="row" className="p-2">{label}</th>{['p10', 'p50', 'p90', 'mean'].map((quantile) => <td key={quantile} className="p-2">{number(commitment.summary[key]?.[quantile])}</td>)}</tr>)}</tbody></table></div>
    <p className="text-body text-ink-secondary">Finite targets with installed Coin rules and these expedition limits: {number(commitment.installed_finite_total)}. Targets with no modeled acquisition path: {number(commitment.unavailable_finite_total)}. Removing access is not additional content runway.</p>
    <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Pouch promises by source</summary><div className="overflow-x-auto"><table className="w-full text-left text-body"><caption className="sr-only">Mean pouch Coins per child</caption><thead><tr>{['Source', 'Granted', 'Opened', 'Pending trip', 'Outstanding including pending'].map((label) => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>{commitment.pouch_sources.map((row) => <tr key={row.source}><th scope="row" className="p-2">{row.source.replaceAll('_', ' ')}</th>{['granted_coins', 'opened_coins', 'pending_coins', 'outstanding_coins'].map((key) => <td key={key} className="p-2">{number(row[key]?.mean)}</td>)}</tr>)}</tbody></table></div></details>
    <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Filtered acquisition paths ({commitment.affected_paths.length})</summary><ul className="space-y-2 text-caption">{commitment.affected_paths.map((row) => <li key={`${row.source}:${row.item_id}`}>{row.name} · {row.source} · requires {number(row.required_coins)} Coins; maximum available {number(row.maximum_available_coins)}.</li>)}</ul></details>
    <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Commitment model assumptions</summary><ul className="list-disc pl-5 space-y-2 text-caption text-ink-secondary">{commitment.assumptions.map((entry) => <li key={entry}>{entry}</li>)}</ul></details>
  </ParchmentCard>;
}
