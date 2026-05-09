// Drop rarities that escalate from the slide-in toast strip to the
// full-screen RareDropReveal modal. Common/uncommon stay in the
// toast strip so a burst of low-value drops doesn't blanket the
// screen, while rare/epic/legendary land as a felt moment.
export const RARE_TIERS = new Set(['rare', 'epic', 'legendary']);
