import { Link } from 'react-router-dom';

export default function PetSuppliesGuide({ food = false }) {
  const title = food ? 'Find food' : 'Find hatching supplies';
  return (
    <section aria-label={title} className="rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3 space-y-2">
      <h3 className="font-semibold text-body text-ink-primary">{title}</h3>
      <p className="text-body text-ink-secondary">
        {food
          ? 'Food can drop from project work, chores, homework, and habits. Some challenges also award food; check their rewards to choose a goal.'
          : 'Earn eggs and potions through everyday activities and challenge rewards. Check challenge rewards for a matching egg and potion bundle, then bring both ingredients here to start incubation.'}
      </p>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-body font-semibold text-sheikah-teal-deep">
        <Link className="inline-flex min-h-11 items-center" to="/quests?tab=trials">View challenge rewards</Link>
        <Link className="inline-flex min-h-11 items-center" to="/quests">Go to tasks</Link>
      </div>
    </section>
  );
}
