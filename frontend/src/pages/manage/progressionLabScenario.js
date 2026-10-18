const clone = (value) => JSON.parse(JSON.stringify(value));
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);

function ordered(value) {
  if (Array.isArray(value)) return value.map(ordered);
  if (isObject(value)) return Object.fromEntries(Object.keys(value).sort().map((key) => [key, ordered(value[key])]));
  return value;
}

export function scenariosMatch(left, right) {
  return JSON.stringify(ordered(left)) === JSON.stringify(ordered(right));
}

export function withPrintQuotes(economy) {
  const rate = economy.printing.minutes_per_coin;
  return {
    ...economy,
    offers: economy.offers.map((offer) => offer.kind === 'printing'
      ? { ...offer, coin_price: rate === null ? 0 : Math.ceil(offer.print_minutes / rate) }
      : offer),
  };
}

export function rewardPolicyLabel(config) {
  return config?.reward_commitment?.enabled ? '100-Coin commitment prototype (75 expeditions / 25 activity pouches)' : rewardBudgetLabel(config?.reward_budget);
}

export function rewardBudgetLabel(budget) {
  return budget?.daily_coins == null ? 'Uncapped per child' : `${budget.daily_coins} Coins per child per day`;
}

function exactKeys(value, keys, message) {
  if (!isObject(value) || Object.keys(value).length !== keys.length || Object.keys(value).some((key) => !keys.includes(key))) throw new Error(message);
}

function validateValue(value, limit, sample, label) {
  if (value === null && limit?.nullable) return;
  const type = limit?.type ?? (sample === null ? 'integer' : typeof sample);
  if ((type === 'integer' || type === 'number') ? !Number.isInteger(value) : typeof value !== type) throw new Error(`The saved value for ${label} has an unsupported type.`);
  if ((limit?.choices && !limit.choices.includes(value)) || (limit?.min != null && value < limit.min) || (limit?.max != null && value > limit.max)
      || (typeof value === 'string' && ((limit?.max_length != null && value.length > limit.max_length) || (limit?.min_length != null && value.length < limit.min_length)))) {
    throw new Error(`The saved value for ${label} is outside the current supported values.`);
  }
}

export function validateEconomy(economy, metadata) {
  const defaults = metadata.economy_defaults ?? metadata.defaults.economy;
  const limits = metadata.economy_limits;
  if (!defaults || !limits) throw new Error('Purchasing assumptions are not supported by these rules.');
  exactKeys(economy, Object.keys(defaults), 'The report must contain complete supported purchasing assumptions.');
  for (const key of Object.keys(defaults).filter((key) => !['printing', 'offers'].includes(key))) {
    validateValue(economy[key], limits.fields[key], defaults[key], key.replaceAll('_', ' '));
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(economy.start_date) || Number.isNaN(Date.parse(`${economy.start_date}T00:00:00Z`))
      || new Date(`${economy.start_date}T00:00:00Z`).toISOString().slice(0, 10) !== economy.start_date
      || economy.start_date < '2000-01-01' || economy.start_date > '2100-12-31') throw new Error('Choose a valid saved start date between 2000 and 2100.');
  exactKeys(economy.printing, Object.keys(defaults.printing), 'The report must contain complete supported printing assumptions.');
  for (const key of Object.keys(defaults.printing)) validateValue(economy.printing[key], limits.printing[key], defaults.printing[key], key.replaceAll('_', ' '));
  if (!Array.isArray(economy.offers) || economy.offers.length > limits.max_offers) throw new Error('The saved routine has too many offers or an invalid offer list.');
  const keys = new Set();
  const offerDefaults = metadata.economy_offer_defaults;
  for (const offer of economy.offers) {
    exactKeys(offer, Object.keys(offerDefaults), 'Every saved offer must contain complete supported fields.');
    for (const key of Object.keys(offerDefaults)) validateValue(offer[key], limits.offer[key], offerDefaults[key], `offer ${key.replaceAll('_', ' ')}`);
    if (!/^[a-z0-9-]{1,40}$/.test(offer.key) || keys.has(offer.key)) throw new Error('Saved offer keys must be unique supported names.');
    if (!offer.label.trim() || offer.label.trim() !== offer.label || offer.label.length > 80) throw new Error('Saved offers need names of up to 80 characters without outer spaces.');
    if (offer.kind === 'printing' && offer.print_minutes < 1) throw new Error('A saved print offer needs at least one print minute.');
    if (offer.kind === 'real_world' && (offer.print_minutes || offer.print_grams)) throw new Error('Saved print resource estimates belong only to print offers.');
    keys.add(offer.key);
  }
  return withPrintQuotes(clone(economy));
}

export function importedScenario(saved, metadata) {
  const config = saved?.config;
  if (saved?.schema_version !== 1 || !isObject(config)) throw new Error('The report must contain a complete supported routine.');
  const defaults = metadata.defaults;
  const flatKeys = Object.keys(defaults).filter((key) => !['economy', 'reward_budget', 'reward_commitment'].includes(key));
  if (Object.keys(config).some((key) => !flatKeys.includes(key) && !['economy', 'reward_budget', 'reward_commitment'].includes(key)) || flatKeys.some((key) => !(key in config))) throw new Error('The report must contain a complete supported routine.');
  for (const key of flatKeys) validateValue(config[key], metadata.limits[key], defaults[key], key.replaceAll('_', ' '));
  const result = clone(config);
  if ('economy' in config) result.economy = validateEconomy(config.economy, metadata);
  else if (metadata.economy_defaults ?? defaults.economy) result.economy = { ...clone(metadata.economy_defaults ?? defaults.economy), enabled: false };
  const budgetDefaults = metadata.reward_budget_defaults ?? defaults.reward_budget;
  if ('reward_budget' in config) {
    if (!budgetDefaults || !metadata.reward_budget_limits) throw new Error('Reward budgets are not supported by these rules.');
    exactKeys(config.reward_budget, Object.keys(budgetDefaults), 'The report must contain complete supported reward budget assumptions.');
    for (const key of Object.keys(budgetDefaults)) validateValue(config.reward_budget[key], metadata.reward_budget_limits[key], budgetDefaults[key], `reward budget ${key.replaceAll('_', ' ')}`);
    result.reward_budget = clone(config.reward_budget);
  } else if (budgetDefaults) result.reward_budget = { ...clone(budgetDefaults), daily_coins: null };
  const commitmentDefaults = metadata.reward_commitment_defaults ?? defaults.reward_commitment;
  if ('reward_commitment' in config) {
    if (!commitmentDefaults) throw new Error('Reward commitments are not supported by these rules.');
    exactKeys(config.reward_commitment, ['enabled'], 'The report must contain a supported commitment policy.');
    if (typeof config.reward_commitment.enabled !== 'boolean') throw new Error('Commitment enabled must be a boolean.');
    result.reward_commitment = clone(config.reward_commitment);
  } else if (commitmentDefaults) result.reward_commitment = { enabled: false };
  if (result.reward_commitment?.enabled && result.reward_budget?.daily_coins != null) throw new Error('Choose either a payout envelope or the commitment prototype.');
  return result;
}
