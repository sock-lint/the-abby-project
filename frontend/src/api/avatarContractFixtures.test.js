import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import defaultCharacter from '../../../contracts/api/fixtures/character-avatar-default.json';
import savedCharacter from '../../../contracts/api/fixtures/character-avatar-saved.json';
import legacyCharacter from '../../../contracts/api/fixtures/character-avatar-legacy.json';
import invalidAppearance from '../../../contracts/api/fixtures/character-avatar-invalid.json';
import avatarCatalog from '../../../contracts/api/fixtures/avatar-catalog.json';
import configuredCharacter from '../../../contracts/api/fixtures/character-avatar-configuration-saved.json';
import invalidConfiguration from '../../../contracts/api/fixtures/character-avatar-configuration-invalid.json';
import { server } from '../test/server';
import { getAvatarCatalog, getCharacterProfile, saveAvatarConfiguration, saveAvatarPreferences } from './index';

describe('saved avatar responses through the shared React API client', () => {
  it('reads the shared equipment catalog and persists a base avatar separately from its accessories', async () => {
    const requests = [];
    let saved = false;
    server.use(
      http.get('*/api/character/avatar/catalog/', ({ request }) => {
        requests.push({ url: request.url, method: request.method });
        return HttpResponse.json(avatarCatalog);
      }),
      http.get('*/api/character/', () => HttpResponse.json(saved ? configuredCharacter : defaultCharacter)),
      http.post('*/api/character/avatar/configuration/', async ({ request }) => {
        requests.push({ url: request.url, method: request.method, body: await request.json() });
        saved = true;
        return HttpResponse.json(configuredCharacter);
      }),
    );
    expect(await getAvatarCatalog()).toEqual(avatarCatalog);
    expect(new URL(requests[0].url).pathname).toBe('/api/character/avatar/catalog/');
    expect(new URL(requests[0].url).searchParams.has('user_id')).toBe(false);
    expect(await getCharacterProfile()).toEqual(defaultCharacter);
    expect(await saveAvatarConfiguration(configuredCharacter.avatar_configuration)).toEqual(configuredCharacter);
    expect(requests[1]).toMatchObject({ method: 'POST', body: { avatar_configuration: configuredCharacter.avatar_configuration } });
    expect(new URL(requests[1].url).pathname).toBe('/api/character/avatar/configuration/');
    expect(new URL(requests[1].url).searchParams.has('user_id')).toBe(false);
    expect(await getCharacterProfile()).toEqual(configuredCharacter);
  });

  it('preserves generic equipment validation errors without retrying or falling back to a different avatar', async () => {
    const requests = [];
    const configuration = { avatar_id: 'unsupported', appearance: {}, accessories: {} };
    server.use(http.post('*/api/character/avatar/configuration/', async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json(invalidConfiguration, { status: 400 });
    }));
    await expect(saveAvatarConfiguration(configuration)).rejects.toMatchObject({ status: 400, response: invalidConfiguration });
    expect(requests).toEqual([{ avatar_configuration: configuration }]);
  });

  it('reads complete defaults, saves only the chosen appearance and preserves the confirmed character', async () => {
    const requests = [];
    let saved = false;
    server.use(
      http.get('*/api/character/', () => HttpResponse.json(saved ? savedCharacter : defaultCharacter)),
      http.post('*/api/character/avatar/', async ({ request }) => {
        requests.push({ url: request.url, body: await request.json() });
        saved = true;
        return HttpResponse.json(savedCharacter);
      }),
    );
    expect(await getCharacterProfile()).toEqual(defaultCharacter);
    expect(await saveAvatarPreferences(savedCharacter.avatar_preferences)).toEqual(savedCharacter);
    expect(requests).toHaveLength(1);
    expect(new URL(requests[0].url).pathname).toBe('/api/character/avatar/');
    expect(requests[0].body).toEqual({ avatar_preferences: savedCharacter.avatar_preferences });
    expect(await getCharacterProfile()).toEqual(savedCharacter);
  });

  it('retains legacy identity without wardrobe and consumes the exact saved equipment choices', async () => {
    server.use(http.get('*/api/character/', () => HttpResponse.json(legacyCharacter)));
    const character = await getCharacterProfile();
    expect(character.avatar_preferences).toEqual({
      hair_style: 'hair-02', hair_color: 'light', skin_tone: 'tan', outfit: 'aqua', outfit_style: 'archer-01', face_style: 'face-01', head_style: 'head-02',
      headwear_style: 'none', mask_style: 'none', bow_style: 'none', quiver_style: 'none',
    });
    expect(savedCharacter.avatar_preferences).toEqual({
      hair_style: 'hair-04', hair_color: 'grey', skin_tone: 'tan', outfit: 'fire', outfit_style: 'archer-03', face_style: 'face-02', head_style: 'head-01',
      headwear_style: 'crown-eve', mask_style: 'mask-undercover', bow_style: 'bow-vines', quiver_style: 'quiver-rook',
    });
  });

  it('preserves validation errors without automatically retrying a rejected save', async () => {
    const requests = [];
    server.use(http.post('*/api/character/avatar/', async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json(invalidAppearance, { status: 400 });
    }));
    await expect(saveAvatarPreferences({ outfit: 'unsupported' })).rejects.toMatchObject({
      status: 400, response: invalidAppearance,
    });
    expect(requests).toEqual([{ avatar_preferences: { outfit: 'unsupported' } }]);
  });
});
