import Button from '../../components/Button';
import SectionHeader from '../../components/SectionHeader';
import { CheckboxField, DateField, SelectField, TextField } from '../../components/form';
import { withPrintQuotes } from './progressionLabScenario';

function Numeric({ label, value, onChange, limit, help, nullable = false, minimum = 0 }) {
  return <TextField label={label} type="number" step="1" min={Math.max(limit?.min ?? minimum, minimum)} max={limit?.max} required={!nullable} value={value ?? ''} helpText={help} onChange={(event) => onChange(event.target.value === '' ? (nullable ? null : '') : Number(event.target.value))} />;
}

function Money({ label, value, onChange, limit, help, nullable = false }) {
  return <TextField label={label} type="number" step="0.01" min="0" max={limit?.max == null ? undefined : limit.max / 100} required={!nullable} value={typeof value === 'string' ? value : value == null ? '' : value / 100} helpText={help}
    onChange={(event) => {
      const raw = event.target.value;
      onChange(raw === '' ? (nullable ? null : '') : /^\d+(?:\.\d{0,2})?$/.test(raw) ? Math.round(Number(raw) * 100) : raw);
    }} />;
}

export default function ProgressionEconomyControls({ economy, metadata, onChange, onExample }) {
  const limits = metadata.economy_limits;
  const update = (key, value) => onChange(withPrintQuotes({ ...economy, [key]: value }));
  const updatePrinting = (key, value) => update('printing', { ...economy.printing, [key]: value });
  const updateOffer = (index, key, value) => update('offers', economy.offers.map((offer, at) => at === index ? { ...offer, [key]: value } : offer));
  const addOffer = (kind) => {
    let index = 1;
    while (economy.offers.some((offer) => offer.key === `reward-${index}`)) index += 1;
    update('offers', [...economy.offers, { ...metadata.economy_offer_defaults, key: `reward-${index}`, kind,
      label: kind === 'printing' ? 'New print' : 'New reward', ...(kind === 'printing' ? { print_minutes: 45 } : {}) }]);
  };
  const move = (index, direction) => {
    const offers = [...economy.offers];
    [offers[index], offers[index + direction]] = [offers[index + direction], offers[index]];
    update('offers', offers);
  };
  return <section aria-label="Purchasing assumptions" className="space-y-3 border-t border-ink-page-shadow pt-4">
    <SectionHeader as="h3" title="Purchasing and family costs">Anonymous scenario offers only. The family shop and saved accounts stay unchanged. Digital item delivery is outside this model.</SectionHeader>
    <CheckboxField label="Model purchases and family costs" checked={economy.enabled} onChange={(event) => update('enabled', event.target.checked)} />
    {!economy.offers.length && <div className="space-y-2"><Button variant="secondary" onClick={onExample}>Load purchasing example (90 days, 10 children)</Button><p className="text-caption text-ink-secondary">Replaces purchasing assumptions with one editable example and explicitly sets the forecast to 90 days and 10 children. Activity choices stay as entered. These example prices are not balance recommendations.</p></div>}
    {economy.enabled && <>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <DateField label="Purchasing start date" value={economy.start_date} min="2000-01-01" max="2100-12-31" required onChange={(event) => update('start_date', event.target.value)} helpText="Sets actual calendar months for budgets; activity day 1 starts on this date." />
        <SelectField label="Purchase strategy" value={economy.purchase_strategy} onChange={(event) => update('purchase_strategy', event.target.value)}>
          <option value="save_for_priority">Save for the first due reward</option><option value="buy_affordable">Buy affordable rewards in order</option>
        </SelectField>
        <Money label="Monthly family cost budget per child ($)" value={economy.monthly_family_budget_cents} limit={limits.fields.monthly_family_budget_cents} nullable onChange={(value) => update('monthly_family_budget_cents', value)} help="Blank = no limit. Zero allows no additional family cost; free rewards can still qualify." />
      </div>
      <p className="text-caption text-ink-secondary">Rewards are considered from top to bottom. Saving waits at the first due reward when Coins, family cost or print limits block it. Buying affordable rewards continues to lower choices.</p>
      <div className="space-y-3">
        {economy.offers.map((offer, index) => <fieldset key={offer.key} className="min-w-0 rounded-lg border border-ink-page-shadow p-3 space-y-3">
          <legend className="px-2 font-semibold text-ink-primary">Reward {index + 1}</legend>
          <div className="flex flex-wrap gap-2"><Button variant="secondary" size="sm" aria-label={`Move reward ${index + 1} earlier`} disabled={index === 0} onClick={() => move(index, -1)}>Move earlier</Button><Button variant="secondary" size="sm" aria-label={`Move reward ${index + 1} later`} disabled={index === economy.offers.length - 1} onClick={() => move(index, 1)}>Move later</Button><Button variant="ghost" size="sm" aria-label={`Remove reward ${index + 1}`} onClick={() => update('offers', economy.offers.filter((_, at) => at !== index))}>Remove</Button></div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <TextField label="Reward name" value={offer.label} maxLength={80} required onChange={(event) => updateOffer(index, 'label', event.target.value)} />
            <SelectField label="Reward type" value={offer.kind} onChange={(event) => {
              const offers = economy.offers.map((row, at) => at === index ? { ...row, kind: event.target.value, print_minutes: event.target.value === 'printing' ? Math.max(1, row.print_minutes) : 0, print_grams: event.target.value === 'printing' ? row.print_grams : 0 } : row);
              update('offers', offers);
            }}><option value="real_world">Real-world reward</option><option value="printing">3D print</option></SelectField>
            {offer.kind === 'real_world' && <Numeric label="Price (Coins)" value={offer.coin_price} limit={limits.offer.coin_price} onChange={(value) => updateOffer(index, 'coin_price', value)} />}
            <Numeric label="Buy again after (days)" value={offer.repeat_every_days} limit={limits.offer.repeat_every_days} onChange={(value) => updateOffer(index, 'repeat_every_days', value)} help="Zero = buy once. Otherwise the wait starts after each successful purchase." />
            <Numeric label="Stock per child (blank = unlimited)" value={offer.stock} limit={limits.offer.stock} nullable onChange={(value) => updateOffer(index, 'stock', value)} help="Lifetime stock for this scenario; zero means sold out. Stock does not reset each month." />
            <Money label="Family cost per purchase ($)" value={offer.family_cost_cents} limit={limits.offer.family_cost_cents} onChange={(value) => updateOffer(index, 'family_cost_cents', value)} help="Your planning estimate, separate from the Coin price. Coins have no cash-out value." />
            {offer.kind === 'printing' && <><Numeric label="Print minutes" value={offer.print_minutes} limit={limits.offer.print_minutes} minimum={1} onChange={(value) => updateOffer(index, 'print_minutes', value)} /><Numeric label="Filament grams" value={offer.print_grams} limit={limits.offer.print_grams} onChange={(value) => updateOffer(index, 'print_grams', value)} /></>}
          </div>
          {offer.kind === 'printing' && <p className="text-body text-ink-secondary">{economy.printing.minutes_per_coin === null ? 'No print rate is set: this print costs 0 Coins in the scenario.' : Number.isFinite(offer.coin_price) ? `Scenario print quote: ${offer.coin_price} Coins for ${offer.print_minutes} minutes at ${economy.printing.minutes_per_coin} minutes per Coin, rounded up.` : 'Enter valid print minutes and a rate to calculate the quote.'}</p>}
        </fieldset>)}
        <div className="flex flex-wrap gap-2"><Button variant="secondary" disabled={economy.offers.length >= limits.max_offers} onClick={() => addOffer('real_world')}>Add reward offer</Button><Button variant="secondary" disabled={economy.offers.length >= limits.max_offers} onClick={() => addOffer('printing')}>Add print offer</Button></div>
        <p className="text-caption text-ink-secondary">Up to {limits.max_offers} offers. Adding offers increases simulation work; longer or busier scenarios may need fewer simulated children.</p>
      </div>
      <details><summary className="min-h-11 py-3 cursor-pointer font-semibold text-ink-primary">Earned money and optional Coin top-ups</summary><div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3">
        <Money label="Money earned per approved chore ($)" value={economy.chore_money_cents} limit={limits.fields.chore_money_cents} onChange={(value) => update('chore_money_cents', value)} />
        <Money label="Money earned per project hour ($)" value={economy.project_hourly_money_cents} limit={limits.fields.project_hourly_money_cents} onChange={(value) => update('project_hourly_money_cents', value)} />
        <CheckboxField label="Top up purchase shortfalls using earned money" checked={economy.exchange_shortfalls} onChange={(event) => update('exchange_shortfalls', event.target.checked)} helpText="Models parent-approved money-to-Coins exchanges only when a due purchase needs Coins. No Coins-to-money cash-out is modeled." />
        {economy.exchange_shortfalls && <Money label="Monthly money-to-Coins exchange limit ($)" value={economy.monthly_exchange_limit_cents} limit={limits.fields.monthly_exchange_limit_cents} nullable onChange={(value) => update('monthly_exchange_limit_cents', value)} help="Blank = no limit; zero prevents top-ups. Only modeled earned money is available." />}
      </div></details>
      <details><summary className="min-h-11 py-3 cursor-pointer font-semibold text-ink-primary">Printing quote and monthly limits</summary><div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3">
        <Numeric label="Print minutes per Coin (blank = free)" value={economy.printing.minutes_per_coin} limit={limits.printing.minutes_per_coin} minimum={1} nullable onChange={(value) => updatePrinting('minutes_per_coin', value)} help="A print costs its minutes divided by this rate, rounded up. Blank means free; no rate is assumed." />
        <Numeric label="Monthly print minutes (blank = unlimited)" value={economy.printing.monthly_minutes} limit={limits.printing.monthly_minutes} nullable onChange={(value) => updatePrinting('monthly_minutes', value)} />
        <Numeric label="Monthly filament grams (blank = unlimited)" value={economy.printing.monthly_grams} limit={limits.printing.monthly_grams} nullable onChange={(value) => updatePrinting('monthly_grams', value)} />
      </div></details>
    </>}
  </section>;
}
