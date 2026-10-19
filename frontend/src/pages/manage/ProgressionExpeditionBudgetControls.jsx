import Button from '../../components/Button';
import { TextField } from '../../components/form';

const examples = [
  ['Unlimited expeditions', null, null],
  ['1 launch per child per day', 1, null],
  ['2 launches per child per day', 2, null],
  ['3 launches per child per day', 3, null],
  ['3 items per child per day', null, 3],
  ['6 items per child per day', null, 6],
  ['9 items per child per day', null, 9],
];

export default function ProgressionExpeditionBudgetControls({ budget, limits, onChange, errors = {}, label = 'Shared expedition limits' }) {
  return <section aria-label={label} className="space-y-3 rounded-lg bg-ink-page-aged p-3">
    <h3 className="font-semibold">{label}</h3>
    <p className="text-body text-ink-secondary">Compare limits shared across all of one child’s mounts. These simulation assumptions are separate from the Coin policy and do not change live rewards.</p>
    <div className="flex flex-wrap gap-2">{examples.map(([name, daily_launches, daily_items]) => <Button key={name} variant="secondary" aria-pressed={budget.daily_launches === daily_launches && budget.daily_items === daily_items} onClick={() => onChange({ daily_launches, daily_items })}>{name}</Button>)}</div>
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{[['daily_launches', 'Daily expedition launches per child'], ['daily_items', 'Daily expedition items per child']].map(([key, name]) => <TextField key={key} label={name} type="number" step="1" min={limits[key].min} max={limits[key].max} value={budget[key] ?? ''} onChange={(event) => onChange({ ...budget, [key]: event.target.value === '' ? null : Number(event.target.value) })} error={errors[`expedition_budget.${key}`]} helpText="Blank means unlimited. Zero disables new launches or item promises. Resets each calendar day; unused capacity does not carry over." />)}</div>
    <p className="text-caption text-ink-secondary">Item limits apply before loot is promised. Each item slot counts once, including a whole Coin pouch or a cosmetic later salvaged. Existing promises pay in full. An item limit still allows Coin-only or empty trips after the item allowance is used.</p>
    {errors.expedition_budget && <p role="alert">{errors.expedition_budget}</p>}
  </section>;
}
