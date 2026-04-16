import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Character from './Character.jsx';
import { server } from '../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('Character', () => {
  it('renders a minimal character profile', async () => {
    server.use(
      http.get('*/api/character/', () =>
        HttpResponse.json({
          display_name: 'Abby',
          username: 'abby',
          level: 3,
          login_streak: 5,
          longest_login_streak: 10,
          perfect_days_count: 2,
          active_frame: null,
          active_title: null,
        }),
      ),
      http.get('*/api/cosmetics/', () => HttpResponse.json({})),
    );
    render(<Character />);
    await waitFor(() => expect(screen.getByText(/abby/i)).toBeInTheDocument());
    expect(screen.getByText(/level 3/i)).toBeInTheDocument();
  });

  it('equips a cosmetic from the owned list', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/character/', () =>
        HttpResponse.json({
          display_name: 'Abby', username: 'abby', level: 1,
          login_streak: 0, longest_login_streak: 0, perfect_days_count: 0,
        }),
      ),
      http.get('*/api/cosmetics/', () =>
        HttpResponse.json({
          active_frame: [{ id: 1, name: 'Gold Frame', sprite_key: 'gold-coin-stack', icon: '🖼️', rarity: 'rare' }],
        }),
      ),
      http.post('*/api/character/equip/', () => HttpResponse.json({})),
    );
    render(<Character />);
    await waitFor(() => expect(screen.getByText(/gold frame/i)).toBeInTheDocument());
    await user.click(screen.getByText(/gold frame/i));
  });

  it('handles equip errors', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/character/', () =>
        HttpResponse.json({
          display_name: 'Abby', username: 'abby', level: 1,
          login_streak: 0, longest_login_streak: 0, perfect_days_count: 0,
        }),
      ),
      http.get('*/api/cosmetics/', () =>
        HttpResponse.json({
          active_title: [{ id: 7, name: 'Adept', sprite_key: null, icon: '👑', rarity: 'common' }],
        }),
      ),
      http.post('*/api/character/equip/', () =>
        HttpResponse.json({ error: 'not owned' }, { status: 400 }),
      ),
    );
    render(<Character />);
    await waitFor(() => expect(screen.getByText(/adept/i)).toBeInTheDocument());
    await user.click(screen.getByText(/adept/i));
    await waitFor(() => expect(screen.getByText(/not owned/i)).toBeInTheDocument());
  });
});
