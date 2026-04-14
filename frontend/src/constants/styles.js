// Shared Tailwind helper classes for the Hyrule Field Notes aesthetic.
// Keep the same export names used across pages so migrations stay minimal.

export const inputClass =
  'w-full bg-ink-page border border-ink-page-shadow rounded-lg px-3 py-2 ' +
  'text-ink-primary text-base placeholder:text-ink-whisper ' +
  'focus:outline-none focus:border-sheikah-teal focus:ring-2 focus:ring-sheikah-teal-glow ' +
  'transition-colors';

// Primary CTA — wax-seal button. Deep sheikah accent with parchment-light text.
export const buttonPrimary =
  'bg-sheikah-teal-deep hover:bg-sheikah-teal disabled:opacity-50 disabled:cursor-not-allowed ' +
  'text-ink-page-rune-glow font-medium rounded-lg transition-colors shadow-sm ' +
  'border border-sheikah-teal-deep/60';

export const buttonSecondary =
  'bg-ink-page-aged hover:bg-ink-page-shadow disabled:opacity-50 ' +
  'text-ink-primary font-medium rounded-lg transition-colors ' +
  'border border-ink-page-shadow';

export const buttonDanger =
  'bg-ember/20 hover:bg-ember/30 disabled:opacity-50 ' +
  'text-ember-deep font-medium rounded-lg transition-colors ' +
  'border border-ember/40';

// Solid-moss success CTA for primary "positive" actions (clock in, submit,
// mark complete, approve). Distinct from the tinted tone used in approve queues.
export const buttonSuccess =
  'bg-moss hover:bg-moss/90 disabled:opacity-50 disabled:cursor-not-allowed ' +
  'text-ink-page-rune-glow font-medium rounded-lg transition-colors ' +
  'border border-moss/70';

export const buttonGhost =
  'text-ink-secondary hover:text-ink-primary transition-colors';

// Card surface helpers — layered parchment + shadow for panels.
export const cardSurface =
  'bg-ink-page-aged border border-ink-page-shadow rounded-xl shadow-[0_1px_0_0_var(--color-ink-page-rune-glow)_inset,0_2px_8px_-4px_rgba(45,31,21,0.25)]';

export const cardSurfacePlain =
  'bg-ink-page-aged/80 border border-ink-page-shadow/60 rounded-xl';

// Heading helpers — pair Cormorant display with a Caveat kicker.
export const headingDisplay = 'font-display text-ink-primary font-semibold tracking-tight';
export const headingScript = 'font-script text-ink-secondary';
