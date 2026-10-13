import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { equipCosmetic, getCosmeticCatalog, getInventory, getPetCodex, getStable, hatchPet } from './index';
import catalog from '../../../contracts/api/fixtures/pets-supported-catalog.json';
import stable from '../../../contracts/api/fixtures/pets-preserved-collection.json';
import cosmetics from '../../../contracts/api/fixtures/cosmetics-supported-catalog.json';
import inventory from '../../../contracts/api/fixtures/items-preserved-inventory.json';
import appearanceInventory from '../../../contracts/api/fixtures/inventory-appearance.json';
import hatchUnavailable from '../../../contracts/api/fixtures/pet-hatch-unavailable.json';
import equipUnavailable from '../../../contracts/api/fixtures/cosmetic-equip-unavailable.json';

describe('current owned-art API contracts', () => {
  it('routes owned color themes to Settings and profile frames to Profile', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json(appearanceInventory)));
    const rows = await getInventory();
    expect(rows).toEqual(appearanceInventory);
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
    expect(await getStable()).toEqual(stable);
    expect(stable.pets.map((pet) => [pet.name, pet.catalog_available])).toEqual([['Peep', true], ['Kit', false]]);
    expect(stable.breeding_available).toBe(false);
    expect(await getCosmeticCatalog()).toEqual(cosmetics);
    expect(cosmetics.active_pet_accessory).toEqual([]);
    expect(await getInventory()).toEqual(inventory);
    const storedAccessory = inventory.find((entry) => entry.item.item_type === 'cosmetic_pet_accessory');
    expect(storedAccessory.quantity).toBe(1);
    expect(storedAccessory.available_actions).toEqual([]);
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
