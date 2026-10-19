import { CheckboxField } from '../../components/form';
import SectionHeader from '../../components/SectionHeader';

export default function ProgressionCommitmentControls({ commitment, onChange, error }) {
  return <section aria-label="Reward commitment prototype" className="space-y-3 border-t border-ink-page-shadow pt-4">
    <SectionHeader as="h3" title="100-Coin commitment prototype">Simulation only. Reserve new reward promises before launch or drop, then pay those promises fully.</SectionHeader>
    <CheckboxField label="Test the 100-Coin commitment prototype" checked={commitment.enabled} onChange={(event) => onChange({ enabled: event.target.checked })} />
    {error && <p role="alert" className="text-ember-deep">{error}</p>}
    <p className="text-caption text-ink-secondary">Each child shares 75 Coins across all expedition mounts and 25 across random activity pouches per day. Short / standard / long expeditions start with 10 / 25 / 50 direct Coins and 1 / 2 / 3 item slots. Less remaining allocation reduces the promise before launch. Item slots filter rewards that cannot be covered in full.</p>
    <p className="text-caption text-ink-secondary">This replaces the hypothetical payout envelope for this run. Owned pouches, frozen trips and authored challenge pouches retain full value. Claims can exceed 100 Coins in a day. Boosts and live reservation storage are not modeled.</p>
  </section>;
}
