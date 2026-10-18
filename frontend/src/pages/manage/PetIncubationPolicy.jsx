import SectionHeader from '../../components/SectionHeader';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { formatIncubationWait, isSupportedIncubationPolicy } from './petIncubationPresentation';

// Reports always use their own recorded policy. The caller must explicitly
// select metadata context when displaying the current model's rules.
export default function PetIncubationPolicy({ policy, context = 'report' }) {
  const current = context === 'metadata';
  const title = current ? 'Current model incubation policy' : 'Recorded incubation policy';
  let unavailable;
  if (policy == null) {
    unavailable = current
      ? 'The current model did not provide an incubation policy. Its incubation wait and care strategy are unavailable.'
      : 'This report did not record an incubation policy. Its incubation wait and care strategy are unrecorded.';
  } else if (!isSupportedIncubationPolicy(policy)) {
    unavailable = `${current ? 'The current model' : 'This report'} contains an incubation policy that this viewer cannot interpret. Its timing and care behavior are unavailable.`;
  }
  return <ParchmentCard as="section" aria-label={title} className="space-y-3">
    <SectionHeader as="h3" title={title}>{!unavailable && (current ? 'These are the current model rules.' : 'This policy was recorded with this report.')}</SectionHeader>
    {unavailable ? <p role="status" className="text-body text-ink-secondary">{unavailable}</p> : <>
      <dl><dt className="text-caption text-ink-secondary">{current ? 'Minimum incubation wait' : 'Recorded minimum incubation wait'}</dt>
        <dd className="text-lede font-semibold text-ink-primary">{formatIncubationWait(policy.duration_seconds)}</dd></dl>
      <ul className="list-disc pl-5 space-y-2 text-body text-ink-secondary">
        <li>Each simulated child can have one unfinished egg at a time.</li>
        <li>The modeled child starts the first compatible egg and potion pair during care.</li>
        <li>The wait keeps running between visits. The egg is hatched during the next active care visit at or after the egg is ready.</li>
        <li>The hatch claim adds the baby companion.</li>
      </ul>
    </>}
  </ParchmentCard>;
}
