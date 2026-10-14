// Shared storybook controls and surfaces, matching Memory Meadow and Play.
// Keep the same export names used across pages so migrations stay minimal.

export const inputClass =
  'w-full min-h-11 bg-ink-page border border-control-border rounded-lg px-4 py-3 ' +
  'text-ink-primary text-base placeholder:text-ink-whisper ' +
  'focus:outline-none focus:border-sheikah-teal-deep focus:ring-2 focus:ring-sheikah-teal-deep ' +
  'transition-colors';

// INTERNAL: these class strings are now consumed only by <Button> and
// <IconButton> (frontend/src/components/Button.jsx). New call sites should
// use the components, not these strings directly.

// Solid accent buttons keep readable foregrounds on every saved cover.
export const buttonPrimary =
  'bg-sheikah-teal-deep hover:bg-sheikah-teal disabled:opacity-50 disabled:cursor-not-allowed ' +
  'text-ink-page-rune-glow font-semibold rounded-full transition-colors shadow-sm ' +
  'border border-sheikah-teal-deep/60';

export const buttonSecondary =
  'bg-ink-page-aged hover:bg-ink-page-shadow disabled:opacity-50 ' +
  'text-ink-primary font-semibold rounded-full transition-colors ' +
  'border border-ink-page-shadow';

export const buttonDanger =
  'bg-ember/20 hover:bg-ember/30 disabled:opacity-50 ' +
  'text-ink-primary font-semibold rounded-full transition-colors ' +
  'border border-ember/40';

// Solid-moss success CTA for primary "positive" actions (clock in, submit,
// mark complete, approve). Distinct from the tinted tone used in approve queues.
export const buttonSuccess =
  'bg-moss hover:bg-moss/90 disabled:opacity-50 disabled:cursor-not-allowed ' +
  'text-ink-page-rune-glow font-semibold rounded-full transition-colors ' +
  'border border-moss/70';

export const buttonGhost =
  'text-ink-secondary hover:text-ink-primary transition-colors';

// Soft panels share the same round edges and quiet shadow as Meadow.
export const cardSurface =
  'bg-ink-page-aged border border-ink-page-shadow rounded-xl shadow-[0_8px_24px_-12px_var(--color-modal-shadow-strong)]';

export const cardSurfacePlain =
  'bg-ink-page-aged/80 border border-ink-page-shadow/60 rounded-xl';

// Legacy font aliases all resolve to the bundled Nunito family.
export const headingDisplay = 'font-display text-ink-primary font-semibold tracking-tight';
export const headingScript = 'font-script text-ink-secondary';

// Form-field text styling — consumed by TextField / SelectField / TextAreaField.
// Kept here so all three primitives stay in lockstep when the journal vocabulary evolves.
export const formLabelClass = 'font-body font-semibold text-body text-ink-secondary mb-2 block';
export const formHelpClass = 'text-caption text-ink-whisper mt-1';
export const formErrorClass = 'text-caption text-ember-deep mt-1';
