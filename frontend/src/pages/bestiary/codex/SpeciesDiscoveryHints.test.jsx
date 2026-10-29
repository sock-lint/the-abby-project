import { describe, expect, it } from 'vitest';
import { renderWithProviders, screen, within } from '../../../test/render';
import { spyHandler } from '../../../test/spy';
import { server } from '../../../test/server';
import SpeciesDetailSheet from './SpeciesDetailSheet';

describe('Collection discovery acquisition hints', () => {
  it('shows each exact appearance eligibility without revealing unowned forms or earning an egg', async () => {
    const post = spyHandler('post', /\/api\//, {});
    server.use(post.handler);
    const species = { id: 1, slug: 'meshtint-wolf', sprite_key: 'meshtint-wolf', name: 'Wolf', catalog_available: true,
      available_potions: [
        { id: 1, slug: 'base', name: 'Base', acquisition_discovery: { name: 'Wolf Egg · Base', eligible: true, path: '/quests?tab=trials' } },
        { id: 2, slug: 'fire', name: 'Fire', acquisition_discovery: { name: 'Wolf Egg · Fire', eligible: false, unavailable_reason: 'Hatch two different companions to unlock rare discoveries.', path: '/quests?tab=trials' } },
      ] };
    const { user } = renderWithProviders(<SpeciesDetailSheet species={species} discoveryEnabled ownership={null} onClose={() => {}} />, { withAuth: false });
    expect(within(screen.getByRole('region', { name: 'Base egg discovery' })).getByText('Wolf Egg · Base is available to choose.')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Fire egg discovery' })).getByText('Hatch two different companions to unlock rare discoveries.')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /Fire Wolf/ })).toBeNull();
    await user.click(within(screen.getByRole('region', { name: 'Base egg discovery' })).getByRole('link', { name: 'View egg discoveries' }));
    expect(post.calls).toHaveLength(0);
  });
});
