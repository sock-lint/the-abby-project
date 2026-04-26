import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Stable from './Stable.jsx';
import { server } from '../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('Stable', () => {
  it('renders empty state when no pets', async () => {
    server.use(
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    render(<Stable />);
    await waitFor(() =>
      expect(screen.getByText(/no companions yet/i)).toBeInTheDocument(),
    );
  });

  it('renders pets and mounts', async () => {
    server.use(
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({
          pets: [{ id: 1, species: { name: 'Drake' }, potion: { name: 'Fire' }, growth_points: 50, is_active: true }],
          mounts: [{ id: 9, species: { name: 'Griffon' }, potion: { name: 'Sky' }, is_active: false }],
          total_possible: 48,
        }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    render(<Stable />);
    await waitFor(() => expect(screen.getByText(/drake/i)).toBeInTheDocument());
    const user = userEvent.setup();
    // Switch to mounts tab if present
    const mountTab = screen.queryByRole('button', { name: /mounts/i });
    if (mountTab) {
      await user.click(mountTab);
      await waitFor(() => expect(screen.getByText(/griffon/i)).toBeInTheDocument());
    }
  });

  it('does not render Hatch or Breed buttons (those moved to the Hatchery tab)', async () => {
    server.use(
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({
          pets: [],
          mounts: [
            { id: 9, species: { icon: '🐺', name: 'Wolf' }, potion: { name: 'Base' }, is_active: false },
            { id: 10, species: { icon: '🦊', name: 'Fox' }, potion: { name: 'Fire' }, is_active: false },
          ],
          total_possible: 48,
        }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    render(<Stable />);
    await screen.findByRole('button', { name: /mounts/i });
    expect(screen.queryByRole('button', { name: /breed mounts/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /hatch pet/i })).toBeNull();
  });
});
