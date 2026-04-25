import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';
import { spyHandler } from '../../test/spy.js';
import FirstEncounterSheet from './FirstEncounterSheet.jsx';

localStorage.setItem('abby_auth_token', 'test-token');

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderSheet() {
  return render(
    <AuthProvider>
      <FirstEncounterSheet pollIntervalMs={100000} />
    </AuthProvider>,
  );
}

describe('FirstEncounterSheet', () => {
  it('renders a new lorebook unlock and marks it seen on dismissal', async () => {
    server.use(
      http.get('*/api/auth/me/', () =>
        HttpResponse.json(buildUser({ role: 'child', lorebook_flags: {} })),
      ),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ newly_unlocked_lorebook: ['pets'] }),
      ),
      http.get('*/api/lorebook/', () =>
        HttpResponse.json({
          counts: { unlocked: 1, total: 1 },
          entries: [
            {
              slug: 'pets',
              title: 'Pets',
              icon: '🐾',
              audience_title: 'The stable hatchery',
              summary: 'Egg + potion companions.',
              kid_voice: 'Pets are companions found along the road.',
              mechanics: [],
              economy: {},
              unlocked: true,
            },
          ],
        }),
      ),
    );
    const patch = spyHandler('patch', /\/api\/auth\/me\/$/, () =>
      HttpResponse.json(
        {
          ...buildUser({ role: 'child' }),
          lorebook_flags: { pets_seen: true },
        },
        {
          headers: { 'Content-Type': 'application/json' },
        },
      ));
    server.use(patch.handler);

    const user = userEvent.setup();
    renderSheet();

    expect(await screen.findByRole('dialog', { name: /new lorebook page/i })).toBeInTheDocument();
    expect(screen.getByText('Pets')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /add it to my lorebook/i }));

    await waitFor(() => expect(patch.calls).toHaveLength(1));
    expect(patch.calls[0].body).toEqual({ lorebook_flags: { pets_seen: true } });
  });
});
