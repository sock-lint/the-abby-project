import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import IssueChallengeForm from './IssueChallengeForm.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderForm(props = {}) {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <IssueChallengeForm
          children={[
            { id: 1, username: 'a', display_label: 'Abby' },
            { id: 2, username: 'b', display_label: 'Beck' },
          ]}
          skills={[]}
          {...props}
        />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('IssueChallengeForm', () => {
  it('hides itself entirely when no children are passed', () => {
    renderForm({ children: [] });
    expect(screen.queryByRole('button', { name: /Issue Challenge/i })).toBeNull();
  });

  it('toggles the form open and shows the assign-to / type selects', async () => {
    renderForm();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Issue Challenge/i }));
    expect(screen.getByRole('combobox', { name: /Assign to/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /^Type$/i })).toBeInTheDocument();
  });

  it('toggling Co-op swaps the single-child select for a multi-child picker', async () => {
    renderForm();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Issue Challenge/i }));
    expect(screen.getByRole('combobox', { name: /Assign to/i })).toBeInTheDocument();
    await user.click(screen.getByLabelText(/Co-op campaign/i));
    expect(screen.queryByRole('combobox', { name: /Assign to/i })).toBeNull();
    expect(screen.getByText(/Co-op participants/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Abby/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Beck/i)).toBeInTheDocument();
  });

  it('submitting a co-op challenge posts coop_user_ids + on_time trigger filter', async () => {
    const createCalls = [];
    server.use(
      http.post('*/api/quests/', async ({ request }) => {
        createCalls.push(await request.clone().json());
        return HttpResponse.json({ id: 99 }, { status: 201 });
      }),
    );

    const onIssued = vi.fn();
    renderForm({ onIssued });
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /Issue Challenge/i }));
    await user.type(screen.getByLabelText(/^Title$/i), 'Tag-team week');
    await user.type(
      screen.getByLabelText(/Description/i),
      'Both kids attack the same boss',
    );
    await user.click(screen.getByLabelText(/Co-op campaign/i));
    await user.click(screen.getByLabelText(/Abby/i));
    await user.click(screen.getByLabelText(/Beck/i));
    await user.click(
      screen.getByLabelText(/Only count homework submitted on time/i),
    );
    await user.click(screen.getByRole('button', { name: /Issue the challenge/i }));

    await waitFor(() => expect(createCalls).toHaveLength(1));
    const body = createCalls[0];
    expect(body.coop_user_ids?.slice().sort()).toEqual([1, 2]);
    expect(body.assigned_to).toBeUndefined();
    expect(body.trigger_filter).toEqual({ on_time: true });
    expect(onIssued).toHaveBeenCalledTimes(1);
  });
});
