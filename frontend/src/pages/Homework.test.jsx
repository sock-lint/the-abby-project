import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Homework from './Homework.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
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
});
