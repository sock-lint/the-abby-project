import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';
import catalogFixture from '../../../contracts/api/fixtures/profile-card-styles-catalog.json';
import ownedFixture from '../../../contracts/api/fixtures/profile-card-styles-owned.json';
import profileFixture from '../../../contracts/api/fixtures/profile-card-style-character.json';
import { renderWithProviders, screen } from '../test/render';
import { server } from '../test/server';
import CosmeticChapter from '../pages/character/CosmeticChapter';
import { COSMETIC_CHAPTERS_BY_SLOT } from '../pages/character/character.constants';
import { getCharacterProfile, getCosmeticCatalog, getCosmetics } from './index';

describe('server-bound Profile card styles', () => {
  it('preserves the same read-only binding through catalog, ownership and saved character responses', async () => {
    server.use(
      http.get('*/api/cosmetics/catalog/', () => HttpResponse.json(catalogFixture)),
      http.get('*/api/cosmetics/', () => HttpResponse.json(ownedFixture)),
      http.get('*/api/character/', () => HttpResponse.json(profileFixture)),
    );
    const [catalog, owned, profile] = await Promise.all([getCosmeticCatalog(), getCosmetics(), getCharacterProfile()]);
    expect(catalog).toEqual(catalogFixture);
    expect(owned).toEqual(ownedFixture);
    expect(profile).toEqual(profileFixture);
    expect(profile.active_frame.metadata).toEqual(owned.active_frame[0].metadata);
    expect(profile.active_frame.metadata).toMatchObject({ border_color: '#3A8B3A', card_asset_id: 'card-front-nature' });
    expect(catalog.active_frame.find((item) => item.id === 402).metadata.card_asset_id).toBe('card-front-light');
    expect(catalog.active_frame.find((item) => item.id === 403).metadata).not.toHaveProperty('card_asset_id');
    expect(owned.active_frame.map((item) => item.id)).toEqual([401]);
  });

  it('keeps the unowned Light style locked while its real earned Nature style can be removed or selected', async () => {
    const user = userEvent.setup();
    const onEquip = vi.fn(), onUnequip = vi.fn();
    const props = {
      chapter: COSMETIC_CHAPTERS_BY_SLOT.active_frame,
      owned: ownedFixture.active_frame,
      catalog: catalogFixture.active_frame,
      activeId: profileFixture.active_frame.id,
      onEquip, onUnequip,
    };
    const { rerender } = renderWithProviders(<CosmeticChapter {...props} />);
    expect(screen.getByText('Nature card style')).toBeInTheDocument();
    expect(screen.getByText('Light card style')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Scholar Frame.*not yet owned/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Scholar Frame/ })).toBeNull();
    await user.click(screen.getByRole('button', { name: /Ranger.*currently equipped/i }));
    expect(onUnequip).toHaveBeenCalledWith('active_frame');
    expect(onEquip).not.toHaveBeenCalled();
    rerender(<CosmeticChapter {...props} activeId={null} />);
    await user.click(screen.getByRole('button', { name: /Ranger.*click to equip/i }));
    expect(onEquip).toHaveBeenCalledWith(401);
  });
});
