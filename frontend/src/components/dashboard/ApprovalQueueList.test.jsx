import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ApprovalQueueList from './ApprovalQueueList.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function renderList(items = [], onDone = () => {}, extraProps = {}) {
  return render(
    <MemoryRouter>
      <ApprovalQueueList items={items} onDone={onDone} {...extraProps} />
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

  it('shows a skeleton instead of "all quiet" while the queue is still loading', () => {
    renderList([], () => {}, { loading: true });
    // An empty array mid-fetch means "we don't know yet" — claiming an
    // all-clear here is how a glancing parent misses pending approvals.
    expect(screen.queryByText(/no pending approvals/i)).not.toBeInTheDocument();
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
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

  it('rejecting a homework submission opens a sheet, captures the note, and posts it', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/homework-submissions\/\d+\/reject\/$/, { ok: true });
    server.use(spy.handler);
    renderList([homework]);

    // Step 1 — clicking the row's Reject button opens the sheet (no request yet).
    await user.click(screen.getByRole('button', { name: /reject math p\.14/i }));
    const sheet = await screen.findByRole('dialog', { name: /reject "math p\.14"/i });
    expect(spy.calls).toHaveLength(0);

    // Step 2 — type a note and submit.
    await user.type(within(sheet).getByLabelText(/note for the kid/i), 'photo too blurry');
    await user.click(within(sheet).getByRole('button', { name: /^reject$/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/homework-submissions\/22\/reject\/$/);
    expect(spy.calls[0].body).toEqual({ notes: 'photo too blurry' });
  });

  it('rejection sheet allows submitting an empty note', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/chore-completions\/\d+\/reject\/$/, { ok: true });
    server.use(spy.handler);
    renderList([chore]);

    await user.click(screen.getByRole('button', { name: /reject dishes/i }));
    const sheet = await screen.findByRole('dialog', { name: /reject "dishes"/i });
    await user.click(within(sheet).getByRole('button', { name: /^reject$/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({ notes: '' });
  });

  it('approving a redemption POSTs with a notes body', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/redemptions\/\d+\/approve\/$/, { ok: true });
    server.use(spy.handler);
    renderList([redemption]);

    await user.click(screen.getByRole('button', { name: /approve ice cream/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/redemptions\/33\/approve\/$/);
    expect(spy.calls[0].body).toEqual({ notes: '' });
  });

  it('surfaces an error message when an approve call fails', async () => {
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

  it('shows "Approve all (N)" per kid when ≥ 2 approvable rows are pending', () => {
    renderList([chore, homework, redemption]);
    // Abby has 2 pending → bulk button rendered.
    expect(
      screen.getByRole('button', { name: /approve all 2 from abby/i }),
    ).toBeInTheDocument();
    // Beck has 1 pending → no bulk button.
    expect(
      screen.queryByRole('button', { name: /approve all 1 from beck/i }),
    ).not.toBeInTheDocument();
  });

  it('bulk approve fans out a request per row and removes them on success', async () => {
    const user = userEvent.setup();
    const choreSpy = spyHandler('post', /\/api\/chore-completions\/\d+\/approve\/$/, { ok: true });
    const homeworkSpy = spyHandler('post', /\/api\/homework-submissions\/\d+\/approve\/$/, { ok: true });
    server.use(choreSpy.handler, homeworkSpy.handler);
    const onDone = vi.fn();
    renderList([chore, homework], onDone);

    await user.click(screen.getByRole('button', { name: /approve all 2 from abby/i }));

    await waitFor(() => {
      expect(choreSpy.calls).toHaveLength(1);
      expect(homeworkSpy.calls).toHaveLength(1);
    });
    expect(choreSpy.calls[0].url).toMatch(/\/chore-completions\/11\/approve\/$/);
    expect(homeworkSpy.calls[0].url).toMatch(/\/homework-submissions\/22\/approve\/$/);
    // Successful rows hide.
    await waitFor(() => {
      expect(screen.queryByText('Dishes')).not.toBeInTheDocument();
      expect(screen.queryByText('Math p.14')).not.toBeInTheDocument();
    });
    expect(onDone).toHaveBeenCalled();
  });

  it('bulk approve leaves a failed row visible with an error chip', async () => {
    const user = userEvent.setup();
    // Chore approve succeeds, homework approve 4xx.
    const choreSpy = spyHandler('post', /\/api\/chore-completions\/\d+\/approve\/$/, { ok: true });
    server.use(
      choreSpy.handler,
      http.post('*/api/homework-submissions/:id/approve/', () =>
        HttpResponse.json({ detail: 'cannot approve' }, { status: 400 }),
      ),
    );
    renderList([chore, homework]);

    await user.click(screen.getByRole('button', { name: /approve all 2 from abby/i }));

    await waitFor(() =>
      expect(screen.queryByText('Dishes')).not.toBeInTheDocument(),
    );
    expect(screen.getByText('Math p.14')).toBeInTheDocument();
    expect(
      screen.getByText(/1 of 2 could not be approved/i),
    ).toBeInTheDocument();
  });

  describe('evidence detail sheet', () => {
    const withProof = {
      id: 51, kind: 'homework', kidId: 3, kidName: 'Abby',
      title: 'Math packet', subtitle: 'submitted on time', reward: null,
      submittedAt: '2026-08-20T10:00:00Z',
      notes: 'Took me two tries',
      proofs: [{ id: 9, image: 'https://example.test/proof.jpg', caption: null }],
    };

    it('shows a thumbnail and opens the work in a sheet', async () => {
      const user = userEvent.setup();
      renderList([withProof]);

      // The photo the kid attached rides along in the payload — show it.
      expect(document.querySelector('img[src="https://example.test/proof.jpg"]')).toBeTruthy();

      await user.click(screen.getByRole('button', { name: /tap to see the work/i }));
      const sheet = await screen.findByRole('dialog', { name: /math packet/i });
      expect(within(sheet).getByText(/took me two tries/i)).toBeInTheDocument();
      expect(within(sheet).getByRole('button', { name: /^approve$/i })).toBeInTheDocument();
    });

    it('surfaces a failed approve inside the sheet and keeps it open', async () => {
      const user = userEvent.setup();
      server.use(
        http.post('*/api/homework-submissions/:id/approve/', () =>
          HttpResponse.json({ detail: 'proof is unreadable' }, { status: 400 }),
        ),
      );
      renderList([withProof]);

      await user.click(screen.getByRole('button', { name: /tap to see the work/i }));
      const sheet = await screen.findByRole('dialog', { name: /math packet/i });
      await user.click(within(sheet).getByRole('button', { name: /^approve$/i }));

      // The failure has to be visible — pre-fix the promise rejected
      // unhandled, the button flipped back to "Approve", and the parent had
      // no way to tell whether the work was approved.
      await waitFor(() =>
        expect(within(sheet).getByRole('alert')).toHaveTextContent(
          /proof is unreadable|could not save/i,
        ),
      );
      // …and the sheet stays open so they can retry or reject.
      expect(
        screen.getByRole('dialog', { name: /math packet/i }),
      ).toBeInTheDocument();
    });

    it('leaves rows without evidence as plain, non-tappable text', () => {
      renderList([{
        id: 7, kind: 'chore', kidId: 3, kidName: 'Abby',
        title: 'Dishes', subtitle: null, reward: 2, submittedAt: null,
      }]);
      expect(screen.queryByText(/tap to see the work/i)).not.toBeInTheDocument();
    });
  });
});
