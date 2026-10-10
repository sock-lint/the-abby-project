import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen } from '../../test/render';
import { buildUser } from '../../test/factories';
import { server } from '../../test/server';
import Meadow from './index';

vi.mock('./meadow.constants', async () => {
  const actual = await vi.importActual('./meadow.constants');
  return {
    ...actual,
    MEADOW_COMPANION: {
      id: 'meadow-dragon', name: 'Your chick', portrait: '/assets/chick-test.png',
      happyPortrait: '/assets/chick-test.png',
    },
  };
});

beforeEach(() => {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    http.get('*/api/chronicle/meadow/', () => HttpResponse.json({ schema_version: 1, keepsake_count: 0, journal_xp_awarded: 0, keepsakes: [] })),
  );
});

describe('Configured Meadow companion', () => {
  it('uses its name and portrait for accessible presentation and keeps its single portrait when greeted', async () => {
    const { user } = renderWithProviders(<Meadow />);
    const portrait = await screen.findByRole('img', { name: 'Your chick' });
    expect(screen.getByRole('region', { name: 'Your chick’s meadow' })).toBeInTheDocument();
    expect(portrait).toHaveAttribute('src', '/assets/chick-test.png');
    expect(screen.queryByRole('img', { name: /dragon/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Say hello' }));
    expect(screen.getByText(/i.m happy you.re here/i)).toBeInTheDocument();
    expect(portrait).toHaveAttribute('src', '/assets/chick-test.png');
  });
});
