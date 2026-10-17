import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { equipCosmetic, getChallenges, getCosmeticCatalog, getInventory, getItemCatalog, getPetCodex, getPetSpeciesCatalog, getQuestCatalog, getRecentDrops, getStable, hatchPet } from './index';
import catalog from '../../../contracts/api/fixtures/pets-supported-catalog.json';
import stable from '../../../contracts/api/fixtures/pets-preserved-collection.json';
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

describe('current owned-art API contracts', () => {
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
    expect(await getPetSpeciesCatalog()).toEqual(imageSpecies);
    expect(imageSpecies[0]).toMatchObject({ catalog_icon: 'portrait-chick', grown_catalog_icon: 'portrait-chick-grown', lifecycle_stages: ['egg', 'baby', 'middle', 'grown'] });
    expect(await getRecentDrops()).toEqual(imageDrops);
    expect(imageDrops[0].item_catalog_icon).toBe('item-fish-cooked');
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
    expect(catalog.species.map((species) => species.slug)).toEqual(['chick']);
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

  it('retains server rejection details for unsupported hatch and accessory requests', async () => {
    const hatch = spyHandler('post', /\/api\/pets\/hatch\/$/, HttpResponse.json(hatchUnavailable, { status: 400 }));
    const equip = spyHandler('post', /\/api\/character\/equip\/$/, HttpResponse.json(equipUnavailable, { status: 400 }));
    server.use(hatch.handler, equip.handler);
    await expect(hatchPet(51, 52)).rejects.toMatchObject({ status: 400, response: hatchUnavailable });
    await expect(equipCosmetic(53)).rejects.toMatchObject({ status: 400, response: equipUnavailable });
    expect(hatch.calls[0].body).toEqual({ egg_item_id: 51, potion_item_id: 52 });
    expect(equip.calls[0].body).toEqual({ item_id: 53 });
  });
});
