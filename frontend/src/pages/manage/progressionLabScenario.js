const clone = (value) => JSON.parse(JSON.stringify(value));
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
export const CHALLENGE_GATE_MODES = { current: 'Current rules', milestones: 'Milestone gates', milestone_tenure: 'Milestone plus tenure gates' };

export function challengeQuestLabel(quest, choices) {
  return choices.filter((entry) => entry.name === quest.name).length > 1 ? `${quest.name} (#${quest.id ?? quest.quest_id})` : quest.name;
}

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

export function expeditionBudgetLabel(budget) {
  const launches = budget?.daily_launches;
  const items = budget?.daily_items;
  if (launches == null && items == null) return 'Unlimited expeditions';
  return [launches == null ? 'Unlimited launches' : `${launches} launch${launches === 1 ? '' : 'es'}`, items == null ? 'unlimited items' : `${items} item${items === 1 ? '' : 's'}`].join(' / ') + ' per child per day';
}

export function challengeGateLabel(gates) {
  return ({ current: 'Current challenge rules', milestones: 'Milestone gates', milestone_tenure: 'Milestone plus tenure gates' })[gates?.mode ?? 'current'] ?? 'Unknown challenge gate policy';
}

const validDate = (value) => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value && value >= '0001-01-01' && value <= '9999-12-31';

export function validateChallengeGates(gates, metadata) {
  if (!metadata.challenge_gates_defaults || !metadata.challenge_gates_limits || !metadata.challenge_gate_choices) throw new Error('Challenge gates are not supported by these rules.');
  exactKeys(gates, ['mode', 'start_date', 'rules'], 'The report must contain complete supported challenge gate assumptions.');
  if (!['current', 'milestones', 'milestone_tenure'].includes(gates.mode) || !validDate(gates.start_date) || gates.start_date > '9998-12-31') throw new Error('Choose a supported saved challenge gate policy and valid calendar start date.');
  if (!Array.isArray(gates.rules) || gates.rules.length > metadata.challenge_gates_limits.max_rules) throw new Error('The saved routine has too many challenge gates or an invalid rule list.');
  const quests = metadata.challenge_gate_choices.quests;
  const skills = metadata.challenge_gate_choices.skills;
  const seen = new Set();
  for (const rule of gates.rules) {
    exactKeys(rule, ['quest_id', 'prerequisite_quest_id', 'skill_id', 'skill_level', 'min_days', 'available_from', 'available_until'], 'Every saved challenge gate must contain complete supported fields.');
    if (!Number.isInteger(rule.quest_id) || !quests.some((quest) => quest.id === rule.quest_id && !quest.is_repeatable) || seen.has(rule.quest_id)) throw new Error('Saved challenge gates need unique available one-time challenge identities.');
    if (rule.prerequisite_quest_id !== null && (!Number.isInteger(rule.prerequisite_quest_id) || rule.prerequisite_quest_id === rule.quest_id || !quests.some((quest) => quest.id === rule.prerequisite_quest_id))) throw new Error('Saved challenge prerequisites must name another available challenge.');
    if (rule.skill_id !== null && (!Number.isInteger(rule.skill_id) || !skills.some((skill) => skill.id === rule.skill_id))) throw new Error('The saved challenge skill is unavailable.');
    if (!Number.isInteger(rule.skill_level) || rule.skill_level < 0 || rule.skill_level > 6 || (rule.skill_id === null && rule.skill_level !== 0) || !Number.isInteger(rule.min_days) || rule.min_days < 0 || rule.min_days > 365) throw new Error('Saved skill levels and elapsed days must be supported whole numbers.');
    if ([rule.available_from, rule.available_until].some((value) => value !== null && !validDate(value)) || (rule.available_from && rule.available_until && rule.available_from > rule.available_until)) throw new Error('Saved challenge availability needs valid dates in chronological order.');
    seen.add(rule.quest_id);
  }
  for (const rule of gates.rules) {
    const visited = new Set([rule.quest_id]);
    let previous = rule.prerequisite_quest_id;
    while (previous !== null) {
      if (visited.has(previous)) throw new Error('Saved challenge prerequisites cannot form a cycle.');
      visited.add(previous);
      previous = gates.rules.find((entry) => entry.quest_id === previous)?.prerequisite_quest_id ?? null;
    }
  }
  return clone(gates);
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
  const nestedKeys = ['economy', 'reward_budget', 'reward_commitment', 'expedition_budget', 'challenge_gates'];
  const flatKeys = Object.keys(defaults).filter((key) => !nestedKeys.includes(key));
  if (Object.keys(config).some((key) => !flatKeys.includes(key) && !nestedKeys.includes(key)) || flatKeys.some((key) => !(key in config))) throw new Error('The report must contain a complete supported routine.');
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
  const expeditionDefaults = metadata.expedition_budget_defaults ?? defaults.expedition_budget;
  if ('expedition_budget' in config) {
    if (!expeditionDefaults || !metadata.expedition_budget_limits) throw new Error('Expedition limits are not supported by these rules.');
    exactKeys(config.expedition_budget, ['daily_launches', 'daily_items'], 'The report must contain complete supported expedition limits.');
    for (const key of ['daily_launches', 'daily_items']) validateValue(config.expedition_budget[key], metadata.expedition_budget_limits[key], expeditionDefaults[key], `expedition ${key.replaceAll('_', ' ')}`);
    result.expedition_budget = clone(config.expedition_budget);
  } else if (expeditionDefaults) result.expedition_budget = { daily_launches: null, daily_items: null };
  if ('challenge_gates' in config) result.challenge_gates = validateChallengeGates(config.challenge_gates, metadata);
  else if (metadata.challenge_gates_defaults ?? defaults.challenge_gates) result.challenge_gates = { ...clone(metadata.challenge_gates_defaults ?? defaults.challenge_gates), mode: 'current', rules: [] };
  return result;
}
