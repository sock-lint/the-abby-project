import SectionHeader from '../../components/SectionHeader';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { formatCurrency } from '../../utils/format';

const number = (value) => Number.isFinite(value) ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value) : 'Unavailable';
const money = (value) => Number.isFinite(value) ? formatCurrency(value / 100) : 'Unavailable';
const stat = (stats, cash = false, key = 'p50') => (cash ? money : number)(stats?.[key]);
const metricRows = [
  ['coins_earned', 'Coins earned from activities', false],
  ['coins_exchanged', 'Coins from money exchanges', false],
  ['coins_spent', 'Coins spent on purchases', false],
  ['coin_balance', 'Coins available at horizon', false],
  ['money_earned_cents', 'Money earned by the child', true],
  ['money_exchanged_cents', 'Earned money exchanged for Coins', true],
  ['money_remaining_cents', 'Earned money still owed to the child', true],
  ['family_cost_cents', 'Estimated reward and print fulfillment cost', true],
  ['parent_liability_cents', 'Fulfillment cost plus money still owed', true],
  ['purchases', 'Successful purchases', false],
  ['blocked_coin_visits', 'Visits blocked by insufficient Coins', false],
  ['blocked_family_budget_visits', 'Visits blocked by family cost budget', false],
  ['blocked_print_budget_visits', 'Visits blocked by print limits', false],
  ['blocked_stock_visits', 'Visits blocked by sold-out stock', false],
  ['print_minutes', 'Print minutes used', false],
  ['print_grams', 'Filament grams used', false],
];

function Reached({ value }) {
  if (!value) return 'Unavailable';
  return <><span className="block">{number(value.completion_rate * 100)}% ({value.completed_trials}/{value.trials})</span>{value.p50_days == null ? <span>Not reached</span> : <span className="block text-caption">Median day {value.p50_days}; earlier {value.p10_days}, later {value.p90_days}</span>}</>;
}

export default function ProgressionEconomyReport({ economy, baseline, config }) {
  if (!economy?.enabled) return null;
  return <ParchmentCard className="space-y-4" as="section" aria-label="Purchasing forecast">
    <SectionHeader as="h3" title="Purchases and family costs">Alternative journeys for one child. Each trial has its own budget; costs are not multiplied by the number of simulated children. Monetary values are dollars; Coins remain a separate currency with no cash-out value.</SectionHeader>
    <p className="text-body text-ink-secondary">Offers are assumed approved and fulfilled immediately. Family costs are your planning estimates. Earned money remaining is still owed to the child; exchanging some of it for Coins does not create another family expense.</p>
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Economy totals, horizontally scrollable">
      <table className="w-full text-body text-left"><caption className="sr-only">Purchasing totals across simulated journeys</caption>
        <thead><tr><th className="p-2">Measure</th><th className="p-2">10th percentile</th><th className="p-2">Median</th><th className="p-2">90th percentile</th><th className="p-2">Mean</th>{baseline && <th className="p-2">Comparison median</th>}</tr></thead>
        <tbody>{metricRows.map(([key, label, cash]) => <tr key={key} className="border-t border-ink-page-shadow"><th scope="row" className="p-2 font-semibold">{label}</th>{['p10', 'p50', 'p90', 'mean'].map((quantile) => <td key={quantile} className="p-2 whitespace-nowrap">{stat(economy.summary[key], cash, quantile)}</td>)}{baseline && <td className="p-2 whitespace-nowrap">{baseline.enabled ? stat(baseline.summary[key], cash) : 'Purchasing was off'}</td>}</tr>)}</tbody>
      </table>
    </div>
    <p className="text-caption text-ink-secondary">Coin and money balances reconcile within each journey. Separate medians can come from different journeys, so adding table medians is not an accounting check.</p>
    <section className="space-y-3" aria-label="Affordability and purchases by reward">
      <SectionHeader as="h4" title="When rewards become affordable and get purchased">Affordability checks only the Coin wallet at an active visit, before purchasing. A purchase also needs available stock and family/print budget. Day ranges use only journeys that reached the event; the completion rate includes every journey.</SectionHeader>
      {economy.offers.length ? <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Reward purchase results, horizontally scrollable"><table className="w-full text-body text-left"><caption className="sr-only">Affordability and actual purchases for each reward</caption><thead><tr><th className="p-2">Reward</th><th className="p-2">Coin price</th><th className="p-2">First Coin-affordable day</th><th className="p-2">First purchase</th><th className="p-2">Purchases (median)</th><th className="p-2">Coins spent (median)</th><th className="p-2">Family cost (median)</th></tr></thead>
        <tbody>{economy.offers.map((offer) => <tr key={offer.key} className="border-t border-ink-page-shadow"><th scope="row" className="p-2 font-semibold">{offer.label}<span className="block text-caption font-normal">{offer.kind === 'printing' ? `${offer.print_minutes} min print · ${offer.print_grams} g` : 'Real-world reward'}</span></th><td className="p-2">{number(offer.coin_price)}</td><td className="p-2"><Reached value={offer.first_coin_affordable} /></td><td className="p-2"><Reached value={offer.first_purchase} /></td><td className="p-2">{stat(offer.purchases)}</td><td className="p-2">{stat(offer.coins_spent)}</td><td className="p-2">{stat(offer.family_cost_cents, true)}</td></tr>)}</tbody>
      </table></div> : <p className="text-body text-ink-secondary">No offers were entered for this scenario.</p>}
    </section>
    <section className="space-y-3" aria-label="Monthly purchasing costs">
      <SectionHeader as="h4" title="Monthly costs and budget blocks">Calendar months start from {config.start_date}. Purchases and flows apply within each listed month. Coin and earned-money balances are closing cumulative balances. The monthly family cost budget is {config.monthly_family_budget_cents === null ? 'unlimited' : money(config.monthly_family_budget_cents)} per child. Partial months receive the full monthly allowance; limits are not prorated.</SectionHeader>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Monthly purchasing results, horizontally scrollable"><table className="w-full text-body text-left"><caption className="sr-only">Calendar month purchasing results, median per child</caption><thead><tr><th className="p-2">Month</th><th className="p-2">Purchases</th><th className="p-2">Coins earned</th><th className="p-2">Coins exchanged</th><th className="p-2">Coins spent</th><th className="p-2">Closing Coins</th><th className="p-2">Money still owed</th><th className="p-2">Family cost</th><th className="p-2">Family budget blocks</th><th className="p-2">Print limit blocks</th><th className="p-2">Stock blocks</th></tr></thead><tbody>{economy.months.map((month) => <tr key={month.month} className="border-t border-ink-page-shadow"><th scope="row" className="p-2 whitespace-nowrap">{month.month}<span className="block text-caption font-normal">Days {month.start_day}–{month.end_day}</span></th>{['purchases', 'coins_earned', 'coins_exchanged', 'coins_spent', 'coin_balance'].map((key) => <td className="p-2" key={key}>{stat(month[key])}</td>)}<td className="p-2">{stat(month.money_remaining_cents, true)}</td><td className="p-2">{stat(month.family_cost_cents, true)}</td><td className="p-2">{stat(month.blocked_family_budget_visits)}</td><td className="p-2">{stat(month.blocked_print_budget_visits)}</td><td className="p-2">{stat(month.blocked_stock_visits)}</td></tr>)}</tbody></table></div>
    </section>
    <details><summary className="min-h-11 py-3 cursor-pointer font-semibold text-ink-primary">Purchasing model assumptions</summary><ul className="list-disc pl-5 space-y-2 text-body text-ink-secondary">{economy.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul><p className="text-caption text-ink-secondary mt-3">Model exchange rate: {number(economy.exchange_rate_coins_per_dollar)} Coins per $1 of earned money. This is a one-way purchase top-up rate, not a cash-out valuation.</p></details>
  </ParchmentCard>;
}
