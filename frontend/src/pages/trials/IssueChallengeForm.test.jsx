import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
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
    expect(screen.queryByRole('button', { name: /Create challenge/i })).toBeNull();
  });

  it('toggles the form open and shows the assign-to / type selects', async () => {
    renderForm();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Create challenge/i }));
    expect(screen.getByRole('combobox', { name: /Assign to/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /^Type$/i })).toBeInTheDocument();
  });

  it('toggling Co-op swaps the single-child select for a multi-child picker', async () => {
    renderForm();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Create challenge/i }));
    expect(screen.getByRole('combobox', { name: /Assign to/i })).toBeInTheDocument();
    await user.click(screen.getByLabelText(/Shared challenge/i));
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

    await user.click(screen.getByRole('button', { name: /Create challenge/i }));
    await user.type(screen.getByLabelText(/^Title$/i), 'Tag-team week');
    await user.type(
      screen.getByLabelText(/Description/i),
      'Both kids attack the same boss',
    );
    await user.click(screen.getByLabelText(/Shared challenge/i));
    await user.click(screen.getByLabelText(/Abby/i));
    await user.click(screen.getByLabelText(/Beck/i));
    await user.click(
      screen.getByLabelText(/Only count homework submitted on time/i),
    );
    await user.click(screen.getByRole('button', { name: /^Assign challenge$/i }));

    await waitFor(() => expect(createCalls).toHaveLength(1));
    const body = createCalls[0];
    expect(body.coop_user_ids?.slice().sort()).toEqual([1, 2]);
    expect(body.assigned_to).toBeUndefined();
    expect(body.trigger_filter).toEqual({ on_time: true });
    expect(onIssued).toHaveBeenCalledTimes(1);
  });

  describe('chip pickers', () => {
    async function openCoopForm(user) {
      await user.click(screen.getByRole('button', { name: /Create challenge/i }));
      await user.click(screen.getByLabelText(/Shared challenge/i));
      await user.click(screen.getByText(/Choose which actions count/i));
    }

    it('gives every co-op and action pill a focus-within ring', async () => {
      renderForm();
      const user = userEvent.setup();
      await openCoopForm(user);
      const coop = within(screen.getByRole('group', { name: /co-op participants/i }))
        .getAllByRole('checkbox');
      const actions = within(screen.getByRole('group', { name: /actions/i }))
        .getAllByRole('checkbox');
      expect(coop).toHaveLength(2);
      expect(actions.length).toBeGreaterThan(0);
      for (const box of [...coop, ...actions]) {
        expect(box.closest('label').className).toMatch(/focus-within:ring/);
      }
    });

    it('exposes the co-op participants as a named group of the child checkboxes', async () => {
      renderForm();
      const user = userEvent.setup();
      await openCoopForm(user);
      const group = screen.getByRole('group', { name: /co-op participants/i });
      expect(within(group).getByRole('checkbox', { name: /Abby/i })).toBeInTheDocument();
      expect(within(group).getByRole('checkbox', { name: /Beck/i })).toBeInTheDocument();
    });

    it('exposes the action pills as a named group of the trigger checkboxes', async () => {
      renderForm();
      const user = userEvent.setup();
      await openCoopForm(user);
      const group = screen.getByRole('group', { name: /actions/i });
      expect(within(group).getByRole('checkbox', { name: /Chore completed/i })).toBeInTheDocument();
      expect(within(group).getByRole('checkbox', { name: /Habit logged/i })).toBeInTheDocument();
    });

    it('still selects pills by keyboard and submits an unchanged body', async () => {
      const createCalls = [];
      server.use(
        http.post('*/api/quests/', async ({ request }) => {
          createCalls.push(await request.clone().json());
          return HttpResponse.json({ id: 99 }, { status: 201 });
        }),
      );
      renderForm();
      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /Create challenge/i }));
      await user.type(screen.getByLabelText(/^Title$/i), 'Keyboard week');
      await user.type(screen.getByLabelText(/Description/i), 'Keys only');
      await user.click(screen.getByLabelText(/Shared challenge/i));

      const abby = screen.getByRole('checkbox', { name: /Abby/i });
      const beck = screen.getByRole('checkbox', { name: /Beck/i });
      abby.focus();
      await user.keyboard(' ');
      await user.tab();
      expect(beck).toHaveFocus();
      await user.keyboard(' ');
      expect(abby).toBeChecked();
      expect(beck).toBeChecked();

      await user.click(screen.getByText(/Choose which actions count/i));
      const chore = screen.getByRole('checkbox', { name: /Chore completed/i });
      chore.focus();
      await user.keyboard(' ');
      expect(chore).toBeChecked();

      await user.click(screen.getByRole('button', { name: /^Assign challenge$/i }));
      await waitFor(() => expect(createCalls).toHaveLength(1));
      const body = createCalls[0];
      expect(body.coop_user_ids.slice().sort()).toEqual([1, 2]);
      expect(body.trigger_filter).toEqual({ allowed_triggers: ['chore_complete'] });
    });
  });
});
