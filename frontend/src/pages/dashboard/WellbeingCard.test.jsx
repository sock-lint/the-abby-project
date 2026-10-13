import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import WellbeingCard from './WellbeingCard.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';
import { buildUser } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

const TODAY = new Date().toISOString().slice(0, 10);

const FRESH_TODAY = {
  id: 7,
  date: TODAY,
  is_today: true,
  affirmation: {
    slug: 'rest-is-progress',
    text: 'Rest is part of the work, not a break from it.',
    tone: 'calm',
  },
  gratitude_lines: [],
  gratitude_paid: false,
  max_lines: 3,
  max_line_chars: 200,
  coin_reward: 2,
};

function renderCard(handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <WellbeingCard />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('WellbeingCard', () => {
  it('renders today’s affirmation text', async () => {
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(FRESH_TODAY)),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/Rest is part of the work/)).toBeInTheDocument(),
    );
  });

  it('Save POSTs the typed gratitude lines and shows a coin chip on first-of-day pay', async () => {
    const user = userEvent.setup();
    const submit = spyHandler('post', /\/api\/wellbeing\/today\/gratitude\/$/, ({ body }) => ({
      ...FRESH_TODAY,
      gratitude_lines: body?.lines || [],
      gratitude_paid: true,
      coin_awarded: 2,
      freshly_paid: true,
    }));
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(FRESH_TODAY)),
      submit.handler,
    ]);
    await waitFor(() =>
      expect(screen.getByText(/Rest is part of the work/)).toBeInTheDocument(),
    );

    const inputs = screen.getAllByRole('textbox');
    expect(inputs).toHaveLength(3);
    await user.type(inputs[0], 'warm bread');
    await user.type(inputs[2], 'a quiet morning');
    await user.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(submit.calls).toHaveLength(1));
    expect(submit.calls[0].body).toEqual({ lines: ['warm bread', 'a quiet morning'] });
    // Coin flash chip appears (role=status separates it from the
    // "first save today earns +2" hint that's always visible).
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(/\+2/),
    );
  });

  it('shows an error toast when no lines are written', async () => {
    const user = userEvent.setup();
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(FRESH_TODAY)),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/Rest is part of the work/)).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() =>
      expect(screen.getByText(/Write at least one line/i)).toBeInTheDocument(),
    );
  });

  it('shows Update label and skips coin chip when today’s row already paid', async () => {
    const paid = { ...FRESH_TODAY, gratitude_paid: true, gratitude_lines: ['previous note'] };
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(paid)),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /update/i })).toBeInTheDocument(),
    );
    // No "first save earns +2" hint when already paid.
    expect(screen.queryByText(/first save today earns/i)).toBeNull();
  });
});
