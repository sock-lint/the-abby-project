import { Link } from 'react-router-dom';
import Button from '../../components/Button';
import SectionHeader from '../../components/SectionHeader';
import ParchmentCard from '../../components/journal/ParchmentCard';
import ProgressionRewardBudgetReport from './ProgressionRewardBudgetReport';
import ProgressionEconomyReport from './ProgressionEconomyReport';
import PetIncubationPolicy from './PetIncubationPolicy';
import { scenariosMatch } from './progressionLabScenario';
import ProgressionExpeditionBudgetReport from './ProgressionExpeditionBudgetReport';
import { expeditionBudgetLabel, rewardPolicyLabel } from './progressionLabScenario';
import ProgressionCommitmentReport from './ProgressionCommitmentReport';
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
export function ProgressionObservations({ observations, loading }) {
  const available = observations?.status === 'observations_available';
  return <ParchmentCard as="section" aria-label="Observed new-user economy" className="space-y-3">
    <SectionHeader as="h3" title="Observed new-user economy">Family-scoped Coin ledger evidence is separate from anonymous simulation results.</SectionHeader>
    {loading && <p role="status">Loading observed Coin evidence…</p>}
    {observations && <>
      <p className="text-caption text-ink-secondary">{observations.period.since} through {observations.period.until} · {observations.period.timezone} · accounts registered within {observations.cohort.registered_within_days} days.</p>
      {!available ? <p role="status">{observations.status === 'insufficient_evidence' ? 'No eligible new-user Coin observations yet.' : 'Observation limits were reached. This bounded read cannot support a conclusion.'}</p> : <><h4 className="font-semibold">Observed installed-economy Coins</h4><dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">{[['Eligible children', observations.cohort.eligible_children], ['Children with Coin entries', observations.activity.ledger_active_children], ['Child-days with Coin entries', observations.activity.ledger_active_child_days], ['Coin credits', observations.ledger.credits], ['Coin debits', observations.ledger.debits], ['Typed automatic-source Coins', observations.automatic_sources.coins], ['Typed-source child-days above 100', observations.automatic_sources.child_days_over_100]].map(([label, value]) => <div key={label}><dt className="text-caption text-ink-secondary">{label}</dt><dd className="text-lede font-semibold">{number(value)}</dd></div>)}</dl>
      {!observations.automatic_sources.attribution_complete && <p role="status" className="text-ember-deep">Attribution is incomplete. Typed automatic-source Coins are a lower bound; unattributed adjustments cannot establish the full source mix.</p>}</>}
      <p className="text-body text-ink-secondary">The 100-Coin policy is not live. Observations describe the installed economy and cannot validate the proposed policy. Coin-entry counts do not measure engagement or retention.</p>
      <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Observation coverage and accounting</summary><ul className="list-disc pl-5 space-y-2 text-caption text-ink-secondary">{observations.notes.map((note) => <li key={note}>{note}</li>)}</ul><pre className="overflow-auto max-h-80 text-caption mt-3">{JSON.stringify({ ledger: observations.ledger, automatic_sources: observations.automatic_sources, cohort: observations.cohort, policy: observations.policy }, null, 2)}</pre></details>
    </>}
  </ParchmentCard>;
}
