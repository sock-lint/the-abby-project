import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Homework from './Homework.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildParent, buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(user, handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Homework />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Homework', () => {
  it('renders for a child with an empty dashboard', async () => {
    renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ assignments: [], submissions: [] }),
      ),
    ]);
    await waitFor(() =>
      expect(
        screen.getAllByText((t) => /homework|study/i.test(t)).length,
      ).toBeGreaterThan(0),
    );
  });

  it('renders for a parent with pending submissions', async () => {
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 9, assignment_title: 'Reading log', user_name: 'Abby', status: 'pending', proofs: [], effort_level: 2, timeliness: 'on_time', subject: 'reading' },
          ],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 3 })])),
    ]);
    await waitFor(() => expect(screen.getByText(/reading log/i)).toBeInTheDocument());
  });

  it('parent approving a submission posts to /homework-submissions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/homework-submissions\/\d+\/approve\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 9, assignment_title: 'Reading log', user_name: 'Abby', status: 'pending', proofs: [], effort_level: 2, timeliness: 'on_time', subject: 'reading', reward_amount_snapshot: '1.00', coin_reward_snapshot: 5 },
          ],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
      approve.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^approve$/i });
    await user.click(button);

    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/homework-submissions\/9\/approve\/$/);
  });

  it('parent rejecting a submission posts to /homework-submissions/{id}/reject/', async () => {
    const user = userEvent.setup();
    const reject = spyHandler('post', /\/api\/homework-submissions\/\d+\/reject\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 9, assignment_title: 'Reading log', user_name: 'Abby', status: 'pending', proofs: [], effort_level: 2, timeliness: 'on_time', subject: 'reading', reward_amount_snapshot: '1.00', coin_reward_snapshot: 5 },
          ],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
      reject.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^reject$/i });
    await user.click(button);

    await waitFor(() => expect(reject.calls).toHaveLength(1));
    expect(reject.calls[0].url).toMatch(/\/homework-submissions\/9\/reject\/$/);
  });
});

// NOTE: child submit-with-proof is not covered here — it requires File/Blob fixtures
// and the downscaleImage canvas pipeline, which deserves its own focused test.
