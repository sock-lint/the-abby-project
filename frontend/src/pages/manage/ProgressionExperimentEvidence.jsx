import { Link } from 'react-router-dom';
import Button from '../../components/Button';
import SectionHeader from '../../components/SectionHeader';
import ProgressionRewardBudgetReport from './ProgressionRewardBudgetReport';
import ProgressionEconomyReport from './ProgressionEconomyReport';
import PetIncubationPolicy from './PetIncubationPolicy';
import { scenariosMatch } from './progressionLabScenario';
import ProgressionExpeditionBudgetReport from './ProgressionExpeditionBudgetReport';
import { challengeGateLabel, expeditionBudgetLabel, rewardPolicyLabel } from './progressionLabScenario';
import ProgressionCommitmentReport from './ProgressionCommitmentReport';
import ProgressionChallengeGateReport from './ProgressionChallengeGateReport';
const number = (value) => Number.isFinite(value) ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value) : 'Not reached or unavailable';
const status = (value) => ({ pass: 'Meets targets', fail: 'Outside targets', insufficient: 'Insufficient evidence', unconfigured: 'No targets configured' })[value] ?? 'Unavailable';
function download(value) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = `abby-experiment-${value.id}.json`; link.click(); URL.revokeObjectURL(url);
}
export function ExperimentComparison({ comparison, dirty }) {
  const { control, candidate, evaluation } = comparison;
  return <section aria-label="Saved experiment comparison" className="space-y-4">
    <SectionHeader as="h3" title="Control and candidate evidence" actions={<Button variant="secondary" onClick={() => download(comparison)}>Download comparison evidence</Button>}>Saved revision {comparison.experiment_revision} · {candidate.config.horizon_days} days · {candidate.config.trials} simulated children · seed {candidate.config.seed}. Both reports use the same routine and catalog snapshot.</SectionHeader>
    {(dirty || comparison.stale || comparison.freshness !== 'current') && <p role="status" className="text-ember-deep">{comparison.freshness === 'unavailable' ? 'Current rules or catalog could not be checked. Saved evidence remains readable; decisions are unavailable.' : 'Evidence is stale or experiment inputs have changed. Save changes and run a fresh comparison before deciding.'}</p>}
    <p className="text-caption text-ink-secondary">Control: {rewardPolicyLabel(control.config)}; {expeditionBudgetLabel(control.config.expedition_budget)}. Candidate: {rewardPolicyLabel(candidate.config)}; {expeditionBudgetLabel(candidate.config.expedition_budget)}.</p>
    <p className="text-caption text-ink-secondary">Challenge policies: control uses {challengeGateLabel(control.config.challenge_gates)}; candidate uses {challengeGateLabel(candidate.config.challenge_gates)}.</p>
    <PetIncubationPolicy policy={candidate.pet_incubation_policy} />
    {candidate.pet_incubation_policy && !scenariosMatch(control.pet_incubation_policy, candidate.pet_incubation_policy) && <p role="status" className="text-ember-deep">The saved reports record different incubation policies. Review their version bindings before interpreting this comparison.</p>}
    <p className="text-body font-semibold">Criteria result: {status(evaluation.status)}.</p>
    <p className="text-caption text-ink-secondary">Criteria apply to absolute candidate values. Day medians include completing journeys only; add a reached-rate criterion to require a share of all children. Rates run from 0 to 1; monetary criteria use cents.</p>
    {evaluation.checks.length > 0 ? <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Experiment criteria, horizontally scrollable"><table className="w-full text-left text-body"><caption className="sr-only">Experiment success criteria</caption><thead><tr>{['Measure', 'Entered range', 'Control', 'Candidate', 'Difference', 'Result'].map((label) => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>{evaluation.checks.map((row) => <tr key={row.metric} className="border-t border-ink-whisper/20"><th scope="row" className="p-2">{row.label}<span className="block text-caption font-normal">{row.unit}</span></th><td className="p-2">{row.min ?? 'No minimum'} – {row.max ?? 'No maximum'}</td>{['control', 'candidate'].map((key) => <td key={key} className="p-2">{number(row[key].value)}{row[key].completed_trials != null && <span className="block text-caption">{row[key].completed_trials}/{row[key].trials} children</span>}</td>)}<td className="p-2">{number(row.delta)}</td><td className="p-2">{status(row.status)}</td></tr>)}</tbody></table></div> : <p>Enter success criteria and rerun before marking the experiment ready for design.</p>}
    <div className="overflow-x-auto"><table className="w-full text-left text-body"><caption className="font-semibold text-left py-2">Progression and content comparison</caption><thead><tr><th className="p-2">Measure</th><th className="p-2">Control</th><th className="p-2">Candidate</th></tr></thead><tbody>{[['Median closing Coins', 'coins_p50'], ['Modeled finite targets', 'finite_content_total'], ['Median targets not completed', 'finite_remaining_p50'], ['Median longest discovery gap (days)', 'longest_novelty_gap_p50']].map(([label, key]) => <tr key={key} className="border-t border-ink-whisper/20"><th scope="row" className="p-2">{label}</th><td className="p-2">{number(control.summary[key])}</td><td className="p-2">{number(candidate.summary[key])}</td></tr>)}</tbody></table></div>
    <p className="text-caption text-ink-secondary">Uncompleted targets include expired challenges. Discovery gaps do not measure boredom or retention.</p>
    {!candidate.reward_commitment?.enabled && <ProgressionRewardBudgetReport budget={candidate.reward_budget} baseline={control.reward_budget} />}
    <ProgressionCommitmentReport commitment={candidate.reward_commitment} />
    <ProgressionExpeditionBudgetReport budget={candidate.expedition_budget} baseline={control.expedition_budget} />
    <ProgressionChallengeGateReport gates={candidate.challenge_gates} baseline={control.challenge_gates} />
    <ProgressionEconomyReport economy={candidate.economy} baseline={control.economy} config={candidate.config.economy} />
    <details><summary className="min-h-11 py-3 cursor-pointer font-semibold">Exact saved assumptions and version bindings</summary><pre className="max-h-80 overflow-auto text-caption">{JSON.stringify({ inputs: comparison.inputs, binding: comparison.binding, created_at: comparison.created_at }, null, 2)}</pre></details>
  </section>;
}
export function RewardProposal({ proposal }) {
  if (!proposal) return null;
  return <section aria-label="Reward design proposal" className="space-y-3">
    <SectionHeader as="h3" title={proposal.title}>Available as an opt-in Lab prototype. Saved comparisons can test this reward table; it is not ready for live rewards.</SectionHeader>
    <p className="text-body text-ink-secondary">Proposed new commitments: {proposal.daily_new_commitment_coins} Coins per child per day, allocating {proposal.allocations.expeditions} to expeditions and {proposal.allocations.activity_pouches} to random activity pouches. Choose the commitment prototype to establish full reward promises before grants. The separate payout envelope omits excess Coins and is only a comparison model.</p>
    <div className="overflow-x-auto"><table className="w-full text-left text-body"><caption className="sr-only">Expedition reward table for the opt-in prototype</caption><thead><tr><th className="p-2">Expedition</th><th className="p-2">Hours</th><th className="p-2">Proposed Coins</th><th className="p-2">Item slots</th></tr></thead><tbody>{proposal.expedition_tiers.map((tier) => <tr key={tier.key} className="border-t border-ink-whisper/20"><th scope="row" className="p-2 capitalize">{tier.key}</th><td className="p-2">{tier.duration_minutes / 60}</td><td className="p-2">{tier.coins}</td><td className="p-2">{tier.item_slots}</td></tr>)}</tbody></table></div>
    <details><summary className="min-h-11 py-3 cursor-pointer font-semibold">Established rewards and design blockers</summary><ul className="list-disc pl-5 space-y-2 text-body text-ink-secondary">{proposal.principles.map((principle) => <li key={principle}>{principle}</li>)}</ul><ul className="space-y-3 mt-4">{proposal.blockers.map((blocker) => <li key={blocker.key}><strong>{blocker.title}</strong><p className="text-caption text-ink-secondary">{blocker.detail}</p><p className="text-body">Next action: {blocker.next_action}</p></li>)}</ul></details>
    <Link to="/manage/rpg-content" className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep underline">Open content workbench for reward versions</Link>
    <p className="text-caption text-ink-secondary">Expedition policy and reservation rules need a reviewed code change. Recording a decision here cannot publish content or approve live changes.</p>
  </section>;
}
export { default as ProgressionObservations } from './ProgressionObservedEconomy';
