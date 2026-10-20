import { describe, expect, it } from 'vitest';
import { importedScenario, scenariosMatch, validateEconomy, withPrintQuotes } from './progressionLabScenario';
import { economyDefaults, economyMetadata, offerDefaults } from './progressionEconomyTestData';
import { gateDefaults, gateMetadata, gateRule } from './progressionChallengeGateTestData';

const copy = (value) => JSON.parse(JSON.stringify(value));
const metadata = { ...economyMetadata, defaults: { seed: 42, economy: economyDefaults }, limits: { seed: { min: 0, max: 2147483647 } } };

describe('Progression scenario preservation', () => {
  it('compares nested values independently of object order and keeps offer priority order meaningful', () => {
    expect(scenariosMatch({ seed: 42, economy: { enabled: true, offers: [1, 2] } }, { economy: { offers: [1, 2], enabled: true }, seed: 42 })).toBe(true);
    expect(scenariosMatch({ offers: [1, 2] }, { offers: [2, 1] })).toBe(false);
  });

  it('loads legacy reports with fresh disabled purchasing assumptions', () => {
    const result = importedScenario({ schema_version: 1, config: { seed: 42 } }, metadata);
    expect(result).toEqual({ seed: 42, economy: economyDefaults });
    result.economy.offers.push({ ...offerDefaults });
    expect(economyDefaults.offers).toEqual([]);
  });

  it('restores legacy reports with an uncapped reward budget and preserves bounded saved budgets', () => {
    const current = { ...metadata, defaults: { ...metadata.defaults, reward_budget: { daily_coins: null } },
      reward_budget_defaults: { daily_coins: null }, reward_budget_limits: { daily_coins: { min: 0, max: 100000, nullable: true } } };
    const legacy = importedScenario({ schema_version: 1, config: { seed: 42 } }, current);
    expect(legacy.reward_budget).toEqual({ daily_coins: null });
    const saved = importedScenario({ schema_version: 1, config: { seed: 42, reward_budget: { daily_coins: 0 } } }, current);
    expect(saved.reward_budget).toEqual({ daily_coins: 0 });
    expect(current.defaults.reward_budget).toEqual({ daily_coins: null });
    for (const reward_budget of [{ daily_coins: -1 }, { daily_coins: 100001 }, { daily_coins: '50' }, { daily_coins: 1.5 }, { daily_coins: 50, child_id: 1 }, {}]) {
      expect(() => importedScenario({ schema_version: 1, config: { seed: 42, reward_budget } }, current)).toThrow();
    }
  });

  it('preserves offer costs and real calendar assumptions while deriving print quotes from minutes and rate', () => {
    const economy = { ...copy(economyDefaults), enabled: true, start_date: '2026-01-20', monthly_family_budget_cents: 600,
      printing: { minutes_per_coin: 10, monthly_minutes: 30, monthly_grams: 20 },
      offers: [{ ...offerDefaults, key: 'print', kind: 'printing', print_minutes: 21, print_grams: 5, coin_price: 900, family_cost_cents: 25 }],
    };
    const result = importedScenario({ schema_version: 1, config: { seed: 17, economy } }, metadata);
    expect(result.economy).toEqual({ ...economy, offers: [{ ...economy.offers[0], coin_price: 3 }] });
    expect(withPrintQuotes({ ...economy, printing: { ...economy.printing, minutes_per_coin: null } }).offers[0].coin_price).toBe(0);
    expect(economy.offers[0].coin_price).toBe(900);
  });

  it.each([
    ['unknown targeting', (row) => { row.user_id = 1; }],
    ['unknown nested printing fields', (row) => { row.printing.printer_id = 4; }],
    ['duplicate offer identity', (row) => { row.offers = [{ ...offerDefaults }, { ...offerDefaults }]; }],
    ['digital delivery', (row) => { row.offers = [{ ...offerDefaults, kind: 'digital_item' }]; }],
    ['string amounts', (row) => { row.chore_money_cents = '500'; }],
    ['negative budget', (row) => { row.monthly_family_budget_cents = -1; }],
    ['invalid dates', (row) => { row.start_date = '2026-02-30'; }],
    ['print without minutes', (row) => { row.offers = [{ ...offerDefaults, kind: 'printing' }]; }],
    ['print resources on real reward', (row) => { row.offers = [{ ...offerDefaults, print_grams: 3 }]; }],
  ])('rejects %s rather than silently dropping saved assumptions', (_name, edit) => {
    const economy = copy(economyDefaults);
    edit(economy);
    expect(() => validateEconomy(economy, metadata)).toThrow();
  });
});


describe('Reward commitment imports', () => {
  const current = { ...metadata, defaults: { ...metadata.defaults, reward_budget: { daily_coins: null }, reward_commitment: { enabled: false } }, reward_budget_defaults: { daily_coins: null }, reward_budget_limits: { daily_coins: { min: 0, max: 100000, nullable: true } }, reward_commitment_defaults: { enabled: false } };
  it('keeps legacy imports disabled and restores the explicit prototype', () => {
    expect(importedScenario({ schema_version: 1, config: { seed: 42 } }, current).reward_commitment).toEqual({ enabled: false });
    expect(importedScenario({ schema_version: 1, config: { seed: 42, reward_commitment: { enabled: true } } }, current).reward_commitment).toEqual({ enabled: true });
  });
  it('rejects mixed or malformed policies instead of silently changing promises', () => {
    for (const reward_commitment of [{ enabled: 'true' }, {}, { enabled: true, coins: 100 }, []]) {
      expect(() => importedScenario({ schema_version: 1, config: { seed: 42, reward_commitment } }, current)).toThrow();
    }
    expect(() => importedScenario({ schema_version: 1, config: { seed: 42, reward_commitment: { enabled: true }, reward_budget: { daily_coins: 100 } } }, current)).toThrow();
  });
});


describe('Shared expedition budget imports', () => {
  const quota = { daily_launches: null, daily_items: null };
  const current = { ...metadata, defaults: { ...metadata.defaults, expedition_budget: quota }, expedition_budget_defaults: quota, expedition_budget_limits: { daily_launches: { min: 0, max: 15, nullable: true }, daily_items: { min: 0, max: 45, nullable: true } } };
  it('defaults old reports to unlimited and preserves explicit zero or combined limits', () => {
    expect(importedScenario({ schema_version: 1, config: { seed: 42 } }, current).expedition_budget).toEqual(quota);
    const expedition_budget = { daily_launches: 0, daily_items: 6 };
    expect(importedScenario({ schema_version: 1, config: { seed: 42, expedition_budget } }, current).expedition_budget).toEqual(expedition_budget);
  });
  it('rejects incomplete, private or incorrectly typed limits', () => {
    for (const expedition_budget of [{}, { daily_launches: 1 }, { ...quota, daily_launches: true }, { ...quota, daily_items: 46 }, { ...quota, daily_launches: -1 }, { ...quota, daily_items: '3' }, { ...quota, daily_items: 1.5 }, { ...quota, user_id: 1 }]) {
      expect(() => importedScenario({ schema_version: 1, config: { seed: 42, expedition_budget } }, current)).toThrow();
    }
  });
});

describe('Challenge gate imports', () => {
  const current = { ...metadata, ...gateMetadata, defaults: { ...metadata.defaults, challenge_gates: gateDefaults } };
  it('keeps historical reports on current rules and restores every explicit gate assumption', () => {
    expect(importedScenario({ schema_version: 1, config: { seed: 42 } }, current).challenge_gates).toEqual(gateDefaults);
    const challenge_gates = { ...gateDefaults, mode: 'milestone_tenure', start_date: '2026-01-04', rules: [gateRule] };
    const result = importedScenario({ schema_version: 1, config: { seed: 42, challenge_gates } }, current);
    expect(result.challenge_gates).toEqual(challenge_gates);
    result.challenge_gates.rules[0].min_days = 20;
    expect(challenge_gates.rules[0].min_days).toBe(14);
  });
  it.each([
    ['unknown policy', (gates) => { gates.mode = 'live'; }],
    ['private targeting', (gates) => { gates.child_id = 42; }],
    ['invalid calendar date', (gates) => { gates.start_date = '2026-02-30'; }],
    ['repeatable target', (gates) => { gates.rules[0].quest_id = 12; }],
    ['unknown challenge', (gates) => { gates.rules[0].quest_id = 999; }],
    ['unknown skill', (gates) => { gates.rules[0].skill_id = 999; }],
    ['duplicate target', (gates) => { gates.rules.push({ ...gateRule }); }],
    ['own prerequisite', (gates) => { gates.rules[0].prerequisite_quest_id = 11; }],
    ['prerequisite cycle', (gates) => { gates.rules.push({ ...gateRule, quest_id: 10, prerequisite_quest_id: 11 }); }],
    ['inverted availability', (gates) => { gates.rules[0].available_until = '2026-01-01'; }],
    ['unknown rule field', (gates) => { gates.rules[0].reward_coins = 100; }],
    ['fractional skill', (gates) => { gates.rules[0].skill_level = 1.5; }],
    ['detached skill level', (gates) => { gates.rules[0].skill_id = null; }],
    ['string elapsed days', (gates) => { gates.rules[0].min_days = '14'; }],
    ['excess tenure', (gates) => { gates.rules[0].min_days = 366; }],
    ['too many rules', (gates) => { gates.rules = Array.from({ length: 21 }, () => ({ ...gateRule })); }],
  ])('rejects %s while preserving the selected inputs', (_name, edit) => {
    const challenge_gates = { ...gateDefaults, rules: [{ ...gateRule }] };
    edit(challenge_gates);
    expect(() => importedScenario({ schema_version: 1, config: { seed: 42, challenge_gates } }, current)).toThrow();
  });
});
