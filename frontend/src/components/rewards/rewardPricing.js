// Editable planning guidance; these figures do not promise daily earnings.
export const REWARD_PLANNING_COINS_PER_ACTIVE_DAY = 50;
export const REWARD_PRICE_TARGETS = [
  { label: 'Small', days: 3 },
  { label: 'Medium', days: 10 },
  { label: 'Big', days: 30 },
];
export const NEW_REWARD_PLANNING_PRICE = REWARD_PLANNING_COINS_PER_ACTIVE_DAY * REWARD_PRICE_TARGETS[0].days;
