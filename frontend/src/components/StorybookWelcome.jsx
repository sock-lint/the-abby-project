import { MEADOW_COMPANION } from '../pages/meadow/meadow.constants';

// Use the same replaceable companion presentation as Meadow, including the
// public fallback when a licensed release bundle is not supplied.
export default function StorybookWelcome({ kicker, description }) {
  return (
    <header className="text-center mb-6">
      <div className="mx-auto mb-4 flex h-24 w-24 items-center justify-center rounded-full bg-moss/10 border border-moss/10">
        <img src={MEADOW_COMPANION.portrait} alt="" aria-hidden="true" width="80" height="80" className="h-20 w-20 object-contain" />
      </div>
      <p className="text-caption font-semibold text-sheikah-teal mb-1">{kicker}</p>
      <h1 className="font-display text-3xl font-bold text-ink-primary leading-tight">The Abby Project</h1>
      <p className="text-body text-ink-secondary mt-3 leading-relaxed">{description}</p>
    </header>
  );
}
