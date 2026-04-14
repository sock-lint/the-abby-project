export const inputClass =
  'w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text text-base focus:outline-none focus:border-amber-primary';

// Button class helpers — use for consistent button styling across pages.
// Compose with additional classes as needed (sizing, width, icon gap, etc.).
export const buttonPrimary =
  'bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold rounded-lg transition-colors';

export const buttonSecondary =
  'bg-forge-muted hover:bg-forge-border disabled:opacity-50 text-forge-text font-medium rounded-lg transition-colors';

export const buttonDanger =
  'bg-red-500/20 hover:bg-red-500/30 disabled:opacity-50 text-red-300 font-medium rounded-lg transition-colors';

// Solid-green CTA — for primary "positive" actions (clock in, submit work,
// mark complete, approve). Distinct from the tinted green used by
// `<ApprovalButtons>` for the approve-queue approve button.
export const buttonSuccess =
  'bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors';

export const buttonGhost =
  'text-forge-text-dim hover:text-forge-text transition-colors';
