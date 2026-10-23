import { useState } from 'react';
import Button from '../Button';
import { TextField } from '../form';
import { REWARD_PLANNING_COINS_PER_ACTIVE_DAY, REWARD_PRICE_TARGETS } from './rewardPricing';

function positiveWholeNumber(value, maximum) {
  if (!/^\d+$/.test(value)) return null;
  const number = Number(value);
  return number >= 1 && number <= maximum ? number : null;
}

export default function RewardPriceGuide({ onApply, disabled = false, maximumPrice = 1_000_000 }) {
  const [dailyEstimate, setDailyEstimate] = useState(String(REWARD_PLANNING_COINS_PER_ACTIVE_DAY));
  const [desiredDays, setDesiredDays] = useState('7');
  const daily = positiveWholeNumber(dailyEstimate, 10_000);
  const days = positiveWholeNumber(desiredDays, 365);
  const customPrice = daily !== null && days !== null && daily * days <= maximumPrice ? daily * days : null;

  return (
    <fieldset className="min-w-0 rounded-lg border border-ink-page-shadow p-3 space-y-3" disabled={disabled}>
      <legend className="px-2 font-semibold text-ink-primary">Price planning</legend>
      <p className="text-caption text-ink-secondary">Choose a suggestion to fill the price, or enter any exact price. Actual earnings vary; active days are days with activities that earn Coins.</p>
      {/* Text inputs keep an unfinished optional estimate from blocking the
          enclosing form's exact-price submission through native validation. */}
      <TextField label="Estimated Coins per active day" inputMode="numeric" value={dailyEstimate} onChange={(event) => setDailyEstimate(event.target.value)} disabled={disabled}
        helpText="A planning estimate you can change. Use a whole number from 1 to 10,000." />
      <div className="flex flex-wrap gap-2">
        {REWARD_PRICE_TARGETS.map(({ label, days: targetDays }) => {
          const coins = daily === null ? null : daily * targetDays;
          return <Button key={label} variant="secondary" size="sm" disabled={disabled || coins === null || coins > maximumPrice} onClick={() => onApply(coins)}>
            {label} · {targetDays} active days{coins === null ? '' : ` · ${coins} Coins`}
          </Button>;
        })}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-end">
        <TextField label="Desired active days" inputMode="numeric" value={desiredDays} onChange={(event) => setDesiredDays(event.target.value)} disabled={disabled}
          helpText="For a custom target, use a whole number from 1 to 365." />
        <Button variant="secondary" disabled={disabled || customPrice === null} onClick={() => onApply(customPrice)}>
          {customPrice === null ? 'Use custom price' : `Use ${customPrice} Coins for ${days} active ${days === 1 ? 'day' : 'days'}`}
        </Button>
      </div>
      {daily === null || days === null ? <p className="text-caption text-ink-secondary">Enter valid whole numbers to use suggestions. Your exact price stays available.</p>
        : daily * days > maximumPrice && <p className="text-caption text-ink-secondary">Choose a smaller estimate or target to keep this suggestion within {maximumPrice.toLocaleString()} Coins.</p>}
    </fieldset>
  );
}
