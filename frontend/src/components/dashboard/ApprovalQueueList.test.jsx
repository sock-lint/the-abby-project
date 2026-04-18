import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ApprovalQueueList from './ApprovalQueueList.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function renderList(items = []) {
  return render(
    <MemoryRouter>
      <ApprovalQueueList items={items} onDone={() => {}} />
    </MemoryRouter>,
  );
}

const chore = {
  id: 11, kind: 'chore', kidId: 1, kidName: 'Abby',
  title: 'Dishes', subtitle: 'Daily', reward: 1.0,
};
const homework = {
  id: 22, kind: 'homework', kidId: 1, kidName: 'Abby',
  title: 'Math p.14', subtitle: 'Due today',
};
const redemption = {
  id: 33, kind: 'redemption', kidId: 2, kidName: 'Beck',
  title: 'Ice cream', subtitle: '50 coins', reward: '50c',
};

describe('ApprovalQueueList', () => {
  it('renders empty state when no pending items', () => {
    renderList([]);
    expect(screen.getByText(/no pending approvals/i)).toBeInTheDocument();
  });

  it('groups items by kid', () => {
    renderList([chore, homework, redemption]);
    expect(screen.getByText('Abby')).toBeInTheDocument();
    expect(screen.getByText('Beck')).toBeInTheDocument();
    expect(screen.getByText('Dishes')).toBeInTheDocument();
    expect(screen.getByText('Math p.14')).toBeInTheDocument();
    expect(screen.getByText('Ice cream')).toBeInTheDocument();
  });

  it('approving a chore POSTs to /chore-completions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/chore-completions\/\d+\/approve\/$/, { ok: true });
    server.use(spy.handler);
    renderList([chore]);

    await user.click(screen.getByRole('button', { name: /approve dishes/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/chore-completions\/11\/approve\/$/);
  });

  it('rejecting a homework submission POSTs to /homework-submissions/{id}/reject/', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/homework-submissions\/\d+\/reject\/$/, { ok: true });
    server.use(spy.handler);
    renderList([homework]);

    await user.click(screen.getByRole('button', { name: /reject math p\.14/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/homework-submissions\/22\/reject\/$/);
  });

  it('approving a redemption POSTs to /redemptions/{id}/approve/ with notes body', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/redemptions\/\d+\/approve\/$/, { ok: true });
    server.use(spy.handler);
    renderList([redemption]);

    await user.click(screen.getByRole('button', { name: /approve ice cream/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/redemptions\/33\/approve\/$/);
    expect(spy.calls[0].body).toEqual({ notes: '' });
  });

  it('surfaces an error message when the mutation fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('*/api/chore-completions/:id/approve/', () =>
        HttpResponse.json({ detail: 'nope' }, { status: 400 }),
      ),
    );
    renderList([chore]);

    await user.click(screen.getByRole('button', { name: /approve dishes/i }));

    await waitFor(() =>
      expect(screen.getByText(/nope|could not save/i)).toBeInTheDocument(),
    );
    // The row stays visible on error.
    expect(screen.getByText('Dishes')).toBeInTheDocument();
  });
});
