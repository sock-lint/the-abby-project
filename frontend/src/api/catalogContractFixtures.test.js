import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { equipCosmetic, getChallenges, getCosmeticCatalog, getInventory, getItemCatalog, getPetCodex, getPetSpeciesCatalog, getQuestCatalog, getRecentDrops, getStable, startIncubation, hatchIncubation } from './index';
import catalog from '../../../contracts/api/fixtures/pets-supported-catalog.json';
import stable from '../../../contracts/api/fixtures/pets-preserved-collection.json';
import sharedExpeditionStable from '../../../contracts/api/fixtures/pets-shared-expedition-allowance.json';
import cosmetics from '../../../contracts/api/fixtures/cosmetics-supported-catalog.json';
import inventory from '../../../contracts/api/fixtures/items-preserved-inventory.json';
import appearanceInventory from '../../../contracts/api/fixtures/inventory-appearance.json';
import hatchUnavailable from '../../../contracts/api/fixtures/pet-hatch-unavailable.json';
import equipUnavailable from '../../../contracts/api/fixtures/cosmetic-equip-unavailable.json';
import imageItems from '../../../contracts/api/fixtures/catalog-icons-items.json';
import imageChallenges from '../../../contracts/api/fixtures/catalog-icons-challenges.json';
import imageSpecies from '../../../contracts/api/fixtures/catalog-icons-species.json';
import imageDrops from '../../../contracts/api/fixtures/catalog-icons-drops.json';
import imageGoals from '../../../contracts/api/fixtures/catalog-icons-goals.json';
import elementalInventory from '../../../contracts/api/fixtures/catalog-icons-elemental-inventory.json';
import elementalChallenges from '../../../contracts/api/fixtures/catalog-icons-elemental-challenges.json';
import elementalCatalog from '../../../contracts/api/fixtures/pets-elemental-supported-catalog.json';
import hatcheryDiscovery from '../../../contracts/api/fixtures/pets-hatchery-discovery.json';
import roster from '../../../shared/catalog/companion-roster.json';
import rosterInventory from '../../../contracts/api/fixtures/inventory-roster-hatching.json';
import rosterIncubation from '../../../contracts/api/fixtures/pet-incubation-roster-start.json';
import rosterHatch from '../../../contracts/api/fixtures/pet-incubation-roster-hatched.json';
import badgeCatalog from '../../../contracts/api/fixtures/badges-rarity-bonuses.json';
import earnedBadges from '../../../contracts/api/fixtures/badges-earned-rarity-bonuses.json';
import retainedLevelBadges from '../../../contracts/api/fixtures/badges-retained-unreachable-level.json';
import reachableLegacyLevels from '../../../contracts/api/fixtures/badges-reachable-legacy-levels.json';
import { getBadges, getEarnedBadges } from './index';

describe('current owned-art API contracts', () => {
  it('transports exact guaranteed acquisition paths without replacing accepted progress with current targets', async () => {
    server.use(http.get('*/api/pets/codex/', () => HttpResponse.json(hatcheryDiscovery)));
    const codex = await getPetCodex();
    expect(codex).toEqual(hatcheryDiscovery);
    const challenges = (species, potion) => codex.species.find((row) => row.slug === species)
      .available_potions.find((row) => row.slug === potion).acquisition_challenges;
    const elemental = codex.species.flatMap((species) => species.available_potions
      .filter((potion) => ['fire', 'ice'].includes(potion.slug))
      .flatMap((potion) => potion.acquisition_challenges));
    expect(elemental.map((row) => row.name).sort()).toEqual([
      'Ember Grove', 'Ember Nest', 'Ember Summit', 'Ember Trail',
      'Frost Grove', 'Frost Nest', 'Frost Summit', 'Frost Trail',
    ]);
    expect(challenges('meshtint-mushroom', 'fire')).toEqual([{
      definition_id: 95, name: 'Ember Grove', offer_available: true, target: '10', duration_days: 180,
      attempt: {
        id: 'goal:401', name: 'My saved Ember Grove', status: 'active',
        progress: '3', target: '8', ends_at: '2027-03-29T19:00:00+00:00', retry_available: false,
      },
      path: '/quests?tab=trials&goal=goal%3A401',
    }]);
    expect(challenges('meshtint-mushroom', 'ice')[0]).toMatchObject({
      attempt: { id: 'goal:402', status: 'expired', progress: '4', target: '10', retry_available: true },
      path: '/quests?tab=trials&goal=goal%3A402',
    });
    expect(challenges('meshtint-dragon', 'fire')[0]).toMatchObject({
      offer_available: false, attempt: { id: 'goal:403', status: 'completed', retry_available: false },
    });
    expect(challenges('chick', 'base')[0]).toMatchObject({
      duration_days: null, attempt: { id: 'goal:406', ends_at: null, progress: '1', target: '2' },
    });
    expect(challenges('meshtint-dragon', 'base')).toEqual([]);
    expect(challenges('meshtint-wolf', 'fire')[0]).toMatchObject({
      attempt: null, path: '/quests?tab=trials',
    });
  });
  it('offers hatching for canonical Fire/Ice potions while same-name copies stay unavailable', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json(elementalInventory)));
    const rows = await getInventory();
    expect(rows).toEqual(elementalInventory);
    expect(new Map(rows.map((row) => [row.item.id, row.item.catalog_icon]))).toEqual(new Map([
      [51, 'item-fire-potion'], [52, 'item-ice-potion'], [53, null], [54, null],
    ]));
    expect(new Set(rows.map((row) => row.id))).toEqual(new Set([101, 102, 103, 104]));
    expect(rows.every((row) => row.quantity === 2)).toBe(true);
    for (const row of rows) {
      const canonical = [51, 52].includes(row.item.id);
      expect(row.item.catalog_available).toBe(canonical);
      expect(row.available_actions).toEqual(canonical ? [{ id: 'hatch', label: 'Hatch a companion', to: '/bestiary?tab=hatchery' }] : []);
    }
    expect(rows.find((row) => row.item.id === 51).item).toMatchObject({
      slug: 'fire-potion', item_type: 'potion', potion_type_name: 'Fire', metadata: { variant: 'fire' },
    });
    expect(rows.find((row) => row.item.id === 52).item).toMatchObject({
      slug: 'ice-potion', item_type: 'potion', potion_type_name: 'Ice', metadata: { variant: 'ice' },
    });
    expect(rows.filter((row) => row.item.name === 'Fire Potion').map((row) => row.item.catalog_icon)).toEqual(['item-fire-potion', null]);
  });

  it('transports sixteen shipped elemental challenge offers and complete reward pairs while custom names stay unbound', async () => {
    server.use(http.get('*/api/quests/catalog/', () => HttpResponse.json(elementalChallenges)));
    const rows = await getQuestCatalog();
    expect(rows).toEqual(elementalChallenges);
    expect(new Map(rows.map((row) => [row.id, row.catalog_icon]))).toEqual(new Map([
      [91, 'challenge-ember-nest'], [92, 'challenge-frost-nest'], [93, 'challenge-ember-trail'], [94, 'challenge-frost-trail'], [95, null],
      [96, 'challenge-ember-grove'], [97, 'challenge-frost-grove'], [98, 'challenge-ember-summit'], [99, 'challenge-frost-summit'],
      [100, 'review-bee-fire-acquisition-icon'], [101, 'review-bee-ice-acquisition-icon'],
      [102, 'review-bat-fire-acquisition-icon'], [103, 'review-bat-ice-acquisition-icon'],
      [104, 'review-snake-fire-acquisition-icon'], [105, 'review-snake-ice-acquisition-icon'],
      [106, 'review-hermit-crab-fire-acquisition-icon'], [107, 'review-hermit-crab-ice-acquisition-icon'],
    ]));
    for (const [id, egg, potion, target, days] of [
      [91, 71, 51, 5, 180], [92, 71, 52, 5, 180], [93, 72, 51, 20, 180], [94, 72, 52, 20, 180],
      [96, 74, 51, 10, 180], [97, 74, 52, 10, 180], [98, 75, 51, 50, 365], [99, 75, 52, 50, 365],
      [100, 76, 51, 5, 180], [101, 76, 52, 5, 180], [102, 73, 51, 10, 180], [103, 73, 52, 10, 180],
      [104, 77, 51, 10, 180], [105, 77, 52, 10, 180], [106, 78, 51, 10, 180], [107, 78, 52, 10, 180],
    ]) {
      const challenge = rows.find((row) => row.id === id);
      expect(challenge).toMatchObject({ quest_type: 'collection', is_system: true, is_repeatable: false, target_value: target, duration_days: days, coin_reward: 0, xp_reward: 0 });
      expect(new Set(challenge.reward_items.map((reward) => reward.item))).toEqual(new Set([egg, potion]));
      expect(challenge.reward_items).toHaveLength(2);
      expect(challenge.reward_items.every((reward) => reward.quantity === 1 && reward.item_catalog_available === true)).toBe(true);
      expect(challenge.reward_items.find((reward) => reward.item_type === 'potion').item_catalog_icon).toBe(potion === 51 ? 'item-fire-potion' : 'item-ice-potion');
    }
    expect(rows.find((row) => row.id === 95)).toMatchObject({ name: 'Ember Nest', is_system: false, catalog_icon: null, reward_items: [] });
  });
  it('uses server-confirmed Fire/Ice compatibility for all eight accepted families', async () => {
    server.use(http.get('*/api/pets/codex/', () => HttpResponse.json(elementalCatalog)));
    const codex = await getPetCodex();
    expect(codex).toEqual(elementalCatalog);
    expect(new Set(codex.potions.map((potion) => potion.slug))).toEqual(new Set(['base', 'fire', 'ice']));
    expect(Object.fromEntries(codex.species.map((species) => [species.slug, species.available_potions.map((potion) => potion.slug)]))).toEqual({
      chick: ['base', 'fire', 'ice'], 'meshtint-wolf': ['base', 'fire', 'ice'], 'meshtint-bat': ['base', 'fire', 'ice'],
      'meshtint-mushroom': ['base', 'fire', 'ice'], 'meshtint-dragon': ['base', 'fire', 'ice'],
      'meshtint-bee': ['base', 'fire', 'ice'], 'meshtint-snake': ['base', 'fire', 'ice'], 'meshtint-hermit-crab': ['base', 'fire', 'ice'],
    });
    expect(Object.fromEntries(codex.species.map((species) => [species.slug, species.id]))).toEqual({
      chick: 61, 'meshtint-wolf': 62, 'meshtint-bat': 63, 'meshtint-mushroom': 64, 'meshtint-dragon': 65,
      'meshtint-bee': 66, 'meshtint-snake': 67, 'meshtint-hermit-crab': 68,
    });
    expect(codex.totals).toEqual({ species: 8, discovered_species: 0, mounts_possible: 24, mounts_owned: 0 });
  });
  it('uses the shared species allowance for every saved potion appearance', async () => {
    server.use(http.get('*/api/pets/stable/', () => HttpResponse.json(sharedExpeditionStable)));
    const stable = await getStable();
    expect(new Set(stable.mounts.map((mount) => mount.potion.slug))).toEqual(new Set(['base', 'fire', 'ice']));
    expect(stable.mounts.every((mount) => mount.expedition_available === false)).toBe(true);
    expect(new Set(stable.mounts.map((mount) => mount.expedition_available_at)).size).toBe(1);
    expect(stable.mounts.every((mount) => mount.expedition_available_in_seconds > 0 && mount.active_expedition === null)).toBe(true);
  });
  it('preserves base coin bonuses in catalog and earned badge responses', async () => {
    server.use(
      http.get('*/api/badges/', () => HttpResponse.json(badgeCatalog)),
      http.get('*/api/badges/earned/', () => HttpResponse.json(earnedBadges)),
    );
    const catalog = await getBadges();
    expect(catalog.results.find((badge) => badge.id === 101)).toMatchObject({ rarity: 'rare', coin_bonus: 35, xp_bonus: 30 });
    expect(catalog.results.find((badge) => badge.id === 102).coin_bonus).toBe(0);
    expect((await getEarnedBadges()).results[0].badge).toMatchObject({ id: 101, rarity: 'rare', coin_bonus: 35 });
  });

  it('retains earned unavailable-level badges while omitting unreachable new goals', async () => {
    const request = spyHandler('get', /\/api\/badges\/$/, retainedLevelBadges);
    server.use(request.handler);
    const response = await getBadges();
    expect(request.calls).toHaveLength(1);
    expect(response).toEqual(retainedLevelBadges);
    expect(response.results.map(({ id }) => id).sort()).toEqual([951, 953]);
    expect(response.results.find(({ id }) => id === 951)).toMatchObject({
      criteria_value: { level: 7 }, catalog_available: false,
    });
    expect(response.results.find(({ id }) => id === 953)).toMatchObject({
      criteria_value: { level: 6 }, catalog_available: true,
    });
  });
  it('transports native-reachable legacy level values without hiding or rewriting their goals', async () => {
    const request = spyHandler('get', /\/api\/badges\/$/, reachableLegacyLevels);
    server.use(request.handler);
    const response = await getBadges();
    expect(request.calls).toHaveLength(1);
    expect(response).toEqual(reachableLegacyLevels);
    expect(new Map(response.results.map(({ id, criteria_value }) => [id, criteria_value.level]))).toEqual(new Map([
      [954, '2'], [955, 1.5], [956, 0], [958, false],
    ]));
    expect(response.results.every(({ catalog_available }) => catalog_available === true)).toBe(true);
    expect(response.results.some(({ id }) => id === 960)).toBe(false);
  });
  it('retains server-verified catalog IDs without deriving identity from shared sprite keys or names', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json(imageItems)),
      http.get('*/api/quests/catalog/', () => HttpResponse.json(imageChallenges)),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json(imageSpecies)),
      http.get('*/api/drops/recent/', () => HttpResponse.json(imageDrops)),
      http.get('*/api/challenges/', () => HttpResponse.json(imageGoals)),
    );
    const items = await getItemCatalog();
    expect(items).toEqual(imageItems);
    const fish = items.filter((item) => item.sprite_key === 'fish');
    expect(fish.map((item) => item.catalog_icon)).toEqual(['item-fish-cooked', 'item-fish', null]);
    expect(items.find((item) => item.name === "Scholar's Draught II").catalog_icon).toBe('item-scholar-draught-ii');
    const challenges = await getQuestCatalog();
    expect(challenges).toEqual(imageChallenges);
    expect(challenges.map((challenge) => challenge.catalog_icon)).toEqual(['challenge-feather-collector', null]);
    expect(challenges[0].reward_items[0].item_catalog_icon).toBe('item-fish');
    expect(challenges[0].reward_items[0]).toMatchObject({ item_rarity: 'common', item_type: 'food', item_catalog_available: true });
    expect(challenges[0].reward_items[0].item_effect_summary).toContain('Adds 5 growth');
    expect(items.find((item) => item.id === 81).acquisition_sources).toEqual([
      { kind: 'challenge', name: 'Feather Collector', path: '/quests?tab=trials' },
    ]);
    expect(await getPetSpeciesCatalog()).toEqual(imageSpecies);
    expect(imageSpecies[0]).toMatchObject({ catalog_icon: 'portrait-chick', grown_catalog_icon: 'portrait-chick-grown', lifecycle_stages: ['egg', 'baby', 'middle', 'grown'] });
    expect(await getRecentDrops()).toEqual(imageDrops);
    expect(imageDrops[0].item_catalog_icon).toBe('item-fish-cooked');
    expect(imageDrops[0]).toMatchObject({ item_type: 'food', item_catalog_available: true, salvage_coins: null });
    expect(imageDrops[0].item_effect_summary).toContain('Adds 5 growth');
    const goals = await getChallenges();
    expect(goals).toEqual(imageGoals);
    expect(goals.results.filter((goal) => goal.origin === 'catalog').map((goal) => goal.catalog_icon)).toEqual(['challenge-feather-collector']);
    expect(goals.results.filter((goal) => goal.origin === 'parent').map((goal) => goal.catalog_icon)).toEqual([null]);
  });
  it('routes owned color themes to Settings and profile frames to Profile', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json(appearanceInventory)));
    const rows = await getInventory();
    expect(rows).toEqual(appearanceInventory);
    expect(rows.find((entry) => entry.item.item_type === 'cosmetic_theme').item).toMatchObject({
      name: 'Twilight Meadow', type_display: 'Color theme', metadata: { theme: 'vigil' },
      catalog_icon: 'item-cover-vigil',
    });
    expect(rows.find((entry) => entry.item.item_type === 'cosmetic_theme').available_actions).toEqual([
      { id: 'equip', label: 'Change color theme', to: '/settings#appearance' },
    ]);
    expect(rows.find((entry) => entry.item.item_type === 'cosmetic_frame').available_actions).toEqual([
      { id: 'equip', label: 'Equip in Profile', to: '/sigil' },
    ]);
  });
  it('keeps supported offers separate from saved ownership', async () => {
    server.use(
      http.get('*/api/pets/codex/', () => HttpResponse.json(catalog)),
      http.get('*/api/pets/stable/', () => HttpResponse.json(stable)),
      http.get('*/api/cosmetics/catalog/', () => HttpResponse.json(cosmetics)),
      http.get('*/api/inventory/', () => HttpResponse.json(inventory)),
    );
    expect(await getPetCodex()).toEqual(catalog);
    expect(catalog.species).toHaveLength(15);
    expect(new Set(catalog.species.map((species) => species.slug))).toEqual(new Set(['chick', ...roster.families.map((family) => family.species_slug)]));
    expect(catalog.potions.map((potion) => potion.slug)).toEqual(['base']);
    expect(catalog.species.every((species) => species.available_potions.length === 1 && species.available_potions[0].slug === 'base')).toBe(true);
    expect(catalog.species.find((species) => species.slug === 'meshtint-bat')).toMatchObject({
      catalog_icon: 'bat-baby-portrait', grown_catalog_icon: 'bat-grown-portrait', rarity: 'uncommon',
    });
    expect(catalog.species.find((species) => species.slug === 'meshtint-dragon')).toMatchObject({ rarity: 'legendary', available_potions: [{ slug: 'base', rarity: 'common' }] });
    expect(catalog.species[0].lifecycle_stages).toEqual(['egg', 'baby', 'middle', 'grown']);
    expect(await getStable()).toEqual(stable);
    expect(stable.pets.map((pet) => [pet.name, pet.catalog_available])).toEqual([['Peep', true], ['Kit', false]]);
    expect(stable.pets.every((pet) => pet.lifecycle_stage === 'baby')).toBe(true);
    expect(stable.breeding_available).toBe(false);
    expect(await getCosmeticCatalog()).toEqual(cosmetics);
    expect(cosmetics.active_pet_accessory).toEqual([]);
    expect(await getInventory()).toEqual(inventory);
    const storedAccessory = inventory.find((entry) => entry.item.item_type === 'cosmetic_pet_accessory');
    expect(storedAccessory.quantity).toBe(1);
    expect(storedAccessory.available_actions).toEqual([]);
    expect(storedAccessory.item.lifecycle_stage).toBeNull();
    const savedEgg = inventory.find((entry) => entry.item.item_type === 'egg');
    expect(savedEgg.item).toMatchObject({ lifecycle_stage: 'egg', pet_species_slug: 'cat', catalog_available: false });
    expect(savedEgg.available_actions).toEqual([]);
  });

  it('preserves a roster egg’s exact namespaced family and its confirmed Base baby after hatching', async () => {
    const calls = [];
    server.use(
      http.get('*/api/inventory/', () => HttpResponse.json(rosterInventory)),
      http.post('*/api/pets/incubations/', async ({ request }) => {
        calls.push(await request.json());
        return HttpResponse.json(rosterIncubation, { status: 201 });
      }),
      http.post('*/api/pets/incubations/1/hatch/', async ({ request }) => {
        calls.push(await request.text());
        return HttpResponse.json(rosterHatch, { status: 201 });
      }),
    );
    const inventory = await getInventory();
    const egg = inventory.find((entry) => entry.item.id === 91);
    expect(egg).toMatchObject({ quantity: 2, item: {
      lifecycle_stage: 'egg', pet_species_slug: 'meshtint-bat',
      metadata: { species: 'meshtint-bat' }, catalog_available: true, catalog_icon: 'bat-egg-portrait',
    } });
    const requestId = '01234567-89ab-4cde-8012-3456789abcde';
    const accepted = await startIncubation(91, 52, requestId);
    expect(accepted.incubation).toMatchObject({ status: 'incubating', remaining_seconds: 86400, pet_id: null, egg: { catalog_icon: 'bat-egg-portrait' } });
    expect(Date.parse(accepted.incubation.ready_at) - Date.parse(accepted.incubation.started_at)).toBe(86400 * 1000);
    const receipt = await hatchIncubation(accepted.incubation.id);
    expect(receipt).toEqual(rosterHatch);
    expect(receipt.server_now).toBe(accepted.incubation.ready_at);
    const pet = receipt.pet;
    expect(pet).toMatchObject({
      species: { slug: 'meshtint-bat', catalog_icon: 'bat-baby-portrait', rarity: 'uncommon' }, potion: { slug: 'base', rarity: 'common' }, rarity: 'uncommon',
      lifecycle_stage: 'baby', growth_points: 0, evolved_to_mount: false, catalog_available: true,
    });
    expect(calls).toEqual([{ egg_item_id: 91, potion_item_id: 52, request_id: requestId }, '']);
  });

  it('retains server rejection details for unsupported hatch and accessory requests', async () => {
    const hatch = spyHandler('post', /\/api\/pets\/incubations\/$/, HttpResponse.json(hatchUnavailable, { status: 400 }));
    const equip = spyHandler('post', /\/api\/character\/equip\/$/, HttpResponse.json(equipUnavailable, { status: 400 }));
    server.use(hatch.handler, equip.handler);
    await expect(startIncubation(51, 52, '01234567-89ab-4cde-8012-3456789abcde')).rejects.toMatchObject({ status: 400, response: hatchUnavailable });
    await expect(equipCosmetic(53)).rejects.toMatchObject({ status: 400, response: equipUnavailable });
    expect(hatch.calls[0].body).toEqual({ egg_item_id: 51, potion_item_id: 52, request_id: '01234567-89ab-4cde-8012-3456789abcde' });
    expect(equip.calls[0].body).toEqual({ item_id: 53 });
  });

});
