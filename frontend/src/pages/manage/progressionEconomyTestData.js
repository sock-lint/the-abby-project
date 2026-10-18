import metadata from '../../../../contracts/api/fixtures/progression-lab-metadata.json';

export const economyDefaults = metadata.economy_defaults;
export const offerDefaults = metadata.economy_offer_defaults;
export const economyMetadata = {
  economy_defaults: economyDefaults, economy_offer_defaults: offerDefaults,
  economy_limits: metadata.economy_limits,
};
const stats = (value) => ({ p10: value, p50: value, p90: value, mean: value });
const reached = { completion_rate: 1 / 3, completed_trials: 1, trials: 3, p10_days: 4, p50_days: 4, p90_days: 4 };
export const economyResult = {
  enabled: true, exchange_rate_coins_per_dollar: 10,
  summary: Object.fromEntries(Object.entries({
    coins_earned: 100, coins_exchanged: 10, coins_spent: 50, coin_balance: 60,
    money_earned_cents: 500, money_exchanged_cents: 100, money_remaining_cents: 400,
    family_cost_cents: 250, parent_liability_cents: 650, purchases: 1,
    blocked_coin_visits: 2, blocked_family_budget_visits: 1, blocked_print_budget_visits: 0,
    blocked_stock_visits: 0, print_minutes: 0, print_grams: 0,
  }).map(([key, value]) => [key, stats(value)])),
  offers: [{ ...offerDefaults, key: 'outing', label: 'Example outing', coin_price: 50,
    first_coin_affordable: { ...reached, completion_rate: 2 / 3, completed_trials: 2, p10_days: 2, p50_days: 3, p90_days: 4 },
    first_purchase: reached, purchases: stats(1), coins_spent: stats(50), family_cost_cents: stats(250),
    blocked_coin_visits: stats(2), blocked_family_budget_visits: stats(1), blocked_print_budget_visits: stats(0), blocked_stock_visits: stats(0),
  }],
  months: [{ month: '2026-01', start_day: 1, end_day: 30,
    ...Object.fromEntries(Object.entries({ purchases: 1, coins_earned: 100, coins_exchanged: 10, coins_spent: 50, coin_balance: 60, money_remaining_cents: 400, family_cost_cents: 250, blocked_family_budget_visits: 1, blocked_print_budget_visits: 0, blocked_stock_visits: 0 }).map(([key, value]) => [key, stats(value)])),
  }],
  assumptions: ['Synthetic offers only; no live fulfillment.'],
};
