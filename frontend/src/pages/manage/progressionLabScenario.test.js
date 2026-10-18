import { describe, expect, it } from 'vitest';
import { importedScenario, scenariosMatch, validateEconomy, withPrintQuotes } from './progressionLabScenario';
import { economyDefaults, economyMetadata, offerDefaults } from './progressionEconomyTestData';

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
