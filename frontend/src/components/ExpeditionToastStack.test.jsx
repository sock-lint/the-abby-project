import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { renderWithProviders } from '../test/render';
import { server } from '../test/server';
import ExpeditionToastStack from './ExpeditionToastStack';

const readyExpedition = {
  id: 33,
  tier: 'standard',
  status: 'active',
  is_ready: true,
  seconds_remaining: 0,
  species_name: 'Griffon',
  species_sprite_key: 'griffon',
  species_icon: '🦅',
  potion_name: 'Sky',
  potion_slug: 'sky',
};

describe('ExpeditionToastStack', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem('abby:expeditions:dismissed');
    }
  });
  afterEach(() => {
    vi.useRealTimers();
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem('abby:expeditions:dismissed');
    }
  });

  it('renders a soft slide-in nudge for a ready-to-claim expedition', async () => {
    server.use(
      http.get('*/api/expeditions/', ({ request }) => {
        const url = new URL(request.url);
        // Hook calls the endpoint with ?ready=true.
        if (url.searchParams.get('ready') === 'true') {
          return HttpResponse.json({ expeditions: [readyExpedition] });
        }
        return HttpResponse.json({ expeditions: [] });
      }),
    );
    renderWithProviders(<ExpeditionToastStack />);
    await waitFor(() => {
      expect(screen.getByText(/Griffon is back/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/standard expedition/i)).toBeInTheDocument();
  });

  it('hides a dismissed expedition and persists the choice in localStorage', async () => {
    server.use(
      http.get('*/api/expeditions/', () =>
        HttpResponse.json({ expeditions: [readyExpedition] }),
      ),
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<ExpeditionToastStack />);
    await waitFor(() => expect(screen.getByText(/Griffon is back/i)).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /dismiss notification/i }));
    await waitFor(() => expect(screen.queryByText(/Griffon is back/i)).toBeNull());

    // localStorage now records the dismissal.
    const stored = JSON.parse(window.localStorage.getItem('abby:expeditions:dismissed'));
    expect(stored).toContain(33);
  });

  it('does not render anything when no expeditions are ready', async () => {
    server.use(
      http.get('*/api/expeditions/', () => HttpResponse.json({ expeditions: [] })),
    );
    renderWithProviders(<ExpeditionToastStack />);
    // No toast text appears even after a poll cycle.
    await waitFor(() => {
      // Use queryAll because the component still renders an empty wrapper.
      expect(screen.queryByText(/is back/i)).toBeNull();
    });
  });
});
