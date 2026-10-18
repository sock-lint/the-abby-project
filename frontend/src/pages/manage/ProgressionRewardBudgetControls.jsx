import Button from '../../components/Button';
import SectionHeader from '../../components/SectionHeader';
import { TextField } from '../../components/form';
import { rewardBudgetLabel } from './progressionLabScenario';

export default function ProgressionRewardBudgetControls({ budget, limits, onChange, error }) {
  return <section aria-label="Reward budget assumptions" className="space-y-3 border-t border-ink-page-shadow pt-4">
    <SectionHeader as="h3" title="Expedition and Coin-pouch budget">Simulation only. Compare one shared daily Coin allowance per child across all their expeditions and Coin pouches. Live rewards stay unchanged.</SectionHeader>
    <div className="flex flex-wrap gap-2" role="group" aria-label="Daily reward budget examples">
      {[null, 50, 100, 150].map((daily_coins) => <Button key={daily_coins ?? 'uncapped'} variant="secondary" aria-pressed={budget.daily_coins === daily_coins} onClick={() => onChange({ daily_coins })}>
        {daily_coins === null ? 'Uncapped' : rewardBudgetLabel({ daily_coins })}
      </Button>)}
    </div>
    <TextField label="Daily reward budget per child (Coins)" type="number" min={limits.daily_coins.min} max={limits.daily_coins.max} step="1"
      value={budget.daily_coins ?? ''} onChange={(event) => onChange({ daily_coins: event.target.value === '' ? null : Number(event.target.value) })}
      error={error} helpText="Blank = uncapped. Zero awards no Coins from these sources. These amounts are comparison examples, not balance recommendations." />
    <p className="text-caption text-ink-secondary">Includes direct expedition Coins, expedition duplicate salvage and every Coin pouch, regardless of where it dropped. Other Coin rewards, earned-money exchanges, XP and items remain outside this allowance. Unused allowance does not carry over; expedition claims use it before pouch openings.</p>
    <p className="text-caption text-ink-secondary">Excess Coins are omitted in the hypothetical journey, not deferred. Modeled pouches are still opened and consumed. This does not describe a live change to held pouches or already-started expeditions. Run an uncapped case, keep it as a comparison, then change the budget and run again with the same routine and seed.</p>
  </section>;
}
