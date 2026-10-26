import SectionHeader from '../../components/SectionHeader';
import ParchmentCard from '../../components/journal/ParchmentCard';

const number = (value) => Number.isFinite(value)
  ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value) : 'Unavailable';
const sourceKinds = {
  recurring: 'Regular earnings', occasional: 'Occasional bonus', manual: 'Manual grant',
  transfer: 'Money exchange', refund: 'Refund', unattributed: 'Unknown source',
};
const tableClass = 'w-full text-left text-body';

function EarningSources({ sources }) {
  return <div className="overflow-x-auto" role="region" aria-label="Coin credit sources, horizontally scrollable" tabIndex={0}>
    <table className={tableClass}>
      <caption className="text-left font-semibold py-2">Where Coin credits came from</caption>
      <thead><tr>{['Source', 'Type', 'Coins', 'Awards or credits'].map((label) => <th key={label} scope="col" className="p-2">{label}</th>)}</tr></thead>
      <tbody>{sources.map((row) => <tr key={row.key} className="border-t border-ink-whisper/20">
        <th scope="row" className="p-2">{row.label}</th><td className="p-2">{sourceKinds[row.kind] ?? 'Unknown source'}</td>
        <td className="p-2">{number(row.coins)}</td><td className="p-2">{number(row.entries)}</td>
      </tr>)}</tbody>
    </table>
    {sources.length === 0 && <p>No Coin credits recorded in this period.</p>}
  </div>;
}

function ShopEarningDays({ pace, rewards }) {
  return <section aria-label="Shop earning estimates" className="space-y-3">
    <h4 className="font-semibold">Shop earning estimates</h4>
    {pace.status === 'available' ? <>
      <p>{number(pace.recurring_coins)} regular Coins ÷ {number(pace.active_child_days)} active child-days = <strong>{number(pace.coins_per_active_day)} Coins per active child-day</strong>.</p>
      {pace.provisional && <p role="status" className="text-ember-deep">Small sample: fewer than 7 active child-days. Treat these estimates as provisional.</p>}
    </> : <p role="status">More saved activity and identified regular earnings are needed before estimating earning days.</p>}
    <p className="text-caption text-ink-secondary">{number(pace.excluded_credits)} Coins excluded from this pace: occasional bonuses, manual grants, money exchanges, refunds and unknown sources. Regular earnings can vary and include random rewards and delayed approvals.</p>
    {!pace.attribution_complete && <p role="status" className="text-ember-deep">Some historical earnings have unknown sources. The measured pace may be lower and earning times longer than the full history would show.</p>}
    <p className="text-caption text-ink-secondary">Each estimate earns the full price from zero using the family’s average across active child-days, rounded up. It ignores existing balances and spending. It is a planning estimate, not a promise or a count of calendar days.</p>
    <div className="overflow-x-auto" role="region" aria-label="Shop estimates, horizontally scrollable" tabIndex={0}>
      <table className={tableClass}>
        <caption className="text-left font-semibold py-2">Active days to earn each shop reward</caption>
        <thead><tr>{['Reward', 'Current price (Coins)', 'Active child-days', 'Availability'].map((label) => <th key={label} scope="col" className="p-2">{label}</th>)}</tr></thead>
        <tbody>{rewards.map((reward) => <tr key={reward.reward_id} className="border-t border-ink-whisper/20">
          <th scope="row" className="p-2">{reward.name}</th><td className="p-2">{number(reward.cost_coins)}</td>
          <td className="p-2">{number(reward.days_to_earn)}</td><td className="p-2">{reward.catalog_available === false ? 'Item unavailable' : reward.stock === 0 ? 'Out of stock' : 'Available'}</td>
        </tr>)}</tbody>
      </table>
      {rewards.length === 0 && <p>No active shop rewards in this report.</p>}
    </div>
  </section>;
}

export default function ProgressionObservedEconomy({ observations, loading }) {
  const limited = observations?.status?.endsWith('_limit_exceeded');
  const modern = Boolean(observations?.earning_pace);
  return <ParchmentCard as="section" aria-label="Observed family coin economy" className="space-y-4">
    <SectionHeader as="h3" title="Observed family coin economy">Saved family activity and actual Coin credits, separate from simulation results.</SectionHeader>
    {loading && <p role="status">Loading observed Coin evidence…</p>}
    {observations && <>
      <p className="text-caption text-ink-secondary">{observations.period.since} through {observations.period.until} · {observations.period.timezone} · {observations.cohort.scope === 'active_family_children' ? 'All currently active children in your family.' : `accounts registered within ${observations.cohort.registered_within_days} days.`}</p>
      {limited ? <p role="status">Observation limits were reached. This bounded read cannot support a conclusion.</p> : <>
        {observations.status === 'insufficient_evidence' && <p role="status">No eligible family activity or Coin observations yet.</p>}
        <h4 className="font-semibold">Observed installed-economy Coins</h4>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">{[
          ['Eligible children', observations.cohort.eligible_children],
          ...(modern ? [['Children with saved work', observations.activity.meaningful_active_children], ['Active child-days with saved work', observations.activity.meaningful_active_child_days]] : []),
          ['Child-days with Coin entries', observations.activity.ledger_active_child_days],
          ['Opening Coins', observations.ledger.opening_balance], ['Coin credits', observations.ledger.credits],
          ['Coin debits', observations.ledger.debits], ['Closing Coins', observations.ledger.closing_balance],
        ].map(([label, value]) => <div key={label}><dt className="text-caption text-ink-secondary">{label}</dt><dd className="text-lede font-semibold">{number(value)}</dd></div>)}</dl>
        {modern ? <>
          <p className="text-caption text-ink-secondary">An active child-day has saved reading, movement, a creation, a positive habit check-in, completed project time, or a pending or approved chore or homework submission. Several activities by one child on the same day count once, even with no Coins. This measures selected saved work, not time spent in the app.</p>
          <EarningSources sources={observations.earning_sources ?? []} />
          <ShopEarningDays pace={observations.earning_pace} rewards={observations.shop_rewards ?? []} />
        </> : <p>This saved report predates activity and shop estimates. Its recorded Coin totals and cohort remain unchanged.</p>}
        {!observations.automatic_sources.attribution_complete && <p role="status" className="text-ember-deep">Attribution is incomplete. Historical adjustments cannot establish the full earning-source mix.</p>}
      </>}
      <p className="text-caption text-ink-secondary">{observations.policy.coins_per_dollar != null && `Money exchange: ${number(observations.policy.coins_per_dollar)} Coins per dollar. `}The 100-Coin policy is not live. These observations cannot validate that proposed policy or measure retention.</p>
      <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Observation coverage and accounting</summary>
        <ul className="list-disc pl-5 space-y-2 text-caption text-ink-secondary">{observations.notes.map((note) => <li key={note}>{note}</li>)}</ul>
        <pre className="overflow-auto max-h-80 text-caption mt-3">{JSON.stringify({ ledger: observations.ledger, automatic_sources: observations.automatic_sources, cohort: observations.cohort, policy: observations.policy }, null, 2)}</pre>
      </details>
    </>}
  </ParchmentCard>;
}
