import { beforeEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen } from '../../test/render';
import { buildUser } from '../../test/factories';
import { server } from '../../test/server';
import Meadow from './index';

beforeEach(() => {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    http.get('*/api/chronicle/meadow/', () => HttpResponse.json({ schema_version: 1, keepsake_count: 0, journal_xp_awarded: 0, keepsakes: [] })),
  );
});

describe('Owned Meadow companion', () => {
  it('shows the server-selected species and greets it without substituting the generic chick', async () => {
    server.use(http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [{
      id: 6, species: { name: 'Fox', sprite_key: 'fox', icon: '🦊' }, potion: { name: 'Base', slug: 'base' },
      is_active: true, growth_points: 25,
    }], mounts: [] })));
    const { user } = renderWithProviders(<Meadow />);
    expect(await screen.findByRole('img', { name: 'Base Fox' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Your companion’s meadow' })).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /chick|dragon/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /show 3d view/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Say hello' }));
    expect(screen.getByText(/hello, base fox/i)).toBeInTheDocument();
  });

  it('keeps capture usable without granting or choosing a pet for an empty collection', async () => {
    renderWithProviders(<Meadow />);
    expect(await screen.findByText(/hatch a pet, then set it active/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Say hello' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Keep a memory' })).toBeEnabled();
    expect(screen.getByRole('link', { name: /hatch & breed/i })).toHaveAttribute('href', '/bestiary?tab=hatchery');
  });
});
