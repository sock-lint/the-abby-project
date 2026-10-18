import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders, screen, userEvent } from '../../test/render.jsx';
import AssignmentCard from './AssignmentCard.jsx';

// The card's "View plan" affordance is a react-router <Link>, so the tree
// needs a router — renderWithProviders supplies MemoryRouter + AuthProvider.
const render = (ui) => renderWithProviders(ui);

function buildAssignment(over = {}) {
  return {
    id: 7,
    title: 'Algebra ch. 4',
    subject: 'math',
    due_date: '2026-04-22',
    effort_level: 3,
    has_project: false,
    submission_status: null,
    project: null,
    ...over,
  };
}

describe('AssignmentCard', () => {
  it('shows management actions without a child Submit action for parents', () => {
    render(<AssignmentCard assignment={buildAssignment()} canManage onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Edit assignment' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Submit' })).not.toBeInTheDocument();
  });
  it('shows the saved assignment instructions without exposing private notes', () => {
    render(<AssignmentCard assignment={buildAssignment({
      description: 'Read pages 12–14, then answer questions 1–3 in complete sentences.',
      notes: 'Private parent planning notes',
    })} onSubmit={vi.fn()} />);

    expect(screen.getByText('Read pages 12–14, then answer questions 1–3 in complete sentences.')).toBeVisible();
    expect(screen.queryByText('Private parent planning notes')).not.toBeInTheDocument();
  });

  it('exports the saved homework due date to Google without private assignment details', async () => {
    const { user } = render(
      <AssignmentCard assignment={buildAssignment({ description: 'Private class notes' })} />,
    );
    await user.click(screen.getByRole('button', { name: 'Add Homework due: Algebra ch. 4 to calendar' }));
    const google = screen.getByRole('link', { name: 'Google Calendar' });
    const event = new URL(google.href).searchParams;
    expect(event.get('text')).toBe('Homework due: Algebra ch. 4');
    expect(event.get('dates')).toBe('20260422/20260423');
    expect(event.get('details')).toContain('/quests?tab=study');
    expect(event.get('details')).not.toContain('Private class notes');
    expect(screen.getByRole('button', { name: 'Apple Calendar (.ics)' })).toBeInTheDocument();
    google.addEventListener('click', (e) => e.preventDefault());
    await user.click(google);
  });

  it('omits calendar export when no due date is saved', () => {
    render(<AssignmentCard assignment={buildAssignment({ due_date: null })} />);
    expect(screen.queryByRole('button', { name: /add .* to calendar/i })).not.toBeInTheDocument();
  });

  it('downloads the saved homework date as an Apple Calendar file', async () => {
    const NativeURL = URL;
    const realSetTimeout = globalThis.setTimeout;
    vi.stubGlobal('URL', class extends NativeURL {
      static createObjectURL = vi.fn(() => 'blob:homework-calendar');
      static revokeObjectURL = vi.fn();
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const timeout = vi.spyOn(globalThis, 'setTimeout').mockImplementation((callback, delay, ...args) => (
      delay === 60000 ? 0 : realSetTimeout(callback, delay, ...args)
    ));
    try {
      const { user } = render(<AssignmentCard assignment={buildAssignment()} />);
      await user.click(screen.getByRole('button', { name: 'Add Homework due: Algebra ch. 4 to calendar' }));
      await user.click(screen.getByRole('button', { name: 'Apple Calendar (.ics)' }));
      expect(click).toHaveBeenCalledTimes(1);
      expect(click.mock.instances[0].download).toBe('Homework-due-Algebra-ch-4.ics');
      const blob = URL.createObjectURL.mock.calls[0][0];
      const content = await new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.readAsText(blob);
      });
      expect(blob.type).toBe('text/calendar;charset=utf-8');
      expect(content).toContain('SUMMARY:Homework due: Algebra ch. 4');
      expect(content).toContain('DTSTART;VALUE=DATE:20260422');
      expect(content).toContain('DTEND;VALUE=DATE:20260423');
      expect(content).toContain('/quests?tab=study');
    } finally {
      click.mockRestore();
      timeout.mockRestore();
      vi.unstubAllGlobals();
    }
  });

  it('fires onSubmit when the child clicks Submit on an un-submitted assignment', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <AssignmentCard
        assignment={buildAssignment()}
        onSubmit={onSubmit}
        onPlan={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        planning={false}
        canPlan={false}
        canManage={false}
      />,
    );
    await user.click(screen.getByRole('button', { name: /submit/i }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('renders the due date through the local-safe formatter, not the raw ISO string', () => {
    render(
      <AssignmentCard
        assignment={buildAssignment({ due_date: '2026-09-03' })}
        onSubmit={vi.fn()}
        onPlan={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        planning={false}
        canPlan={false}
        canManage={false}
      />,
    );
    // The bare backend value must not reach the kid-facing card.
    expect(screen.queryByText(/2026-09-03/)).toBeNull();
    const expected = new Date(2026, 8, 3).toLocaleDateString();
    expect(screen.getByText(`due ${expected}`)).toBeInTheDocument();
  });

  it('hides Submit once a submission exists, swaps in View plan when a project is attached', () => {
    render(
      <AssignmentCard
        assignment={buildAssignment({
          submission_status: { status: 'pending' },
          has_project: true,
          project: 42,
        })}
        onSubmit={vi.fn()}
        onPlan={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        planning={false}
        canPlan={false}
        canManage={false}
      />,
    );
    expect(screen.queryByRole('button', { name: /submit/i })).toBeNull();
    const view = screen.getByRole('link', { name: /view plan/i });
    expect(view).toHaveAttribute('href', '/quests/ventures/42');
  });

  it('View plan navigates client-side instead of reloading the PWA', async () => {
    const { user } = renderWithProviders(
      <Routes>
        <Route
          path="/"
          element={(
            <AssignmentCard
              assignment={buildAssignment({
                submission_status: { status: 'pending' },
                has_project: true,
                project: 42,
              })}
              onSubmit={vi.fn()}
              onPlan={vi.fn()}
              onEdit={vi.fn()}
              onDelete={vi.fn()}
              planning={false}
              canPlan={false}
              canManage={false}
            />
          )}
        />
        <Route path="/quests/ventures/:id" element={<div>project plan page</div>} />
      </Routes>,
    );
    await user.click(screen.getByRole('link', { name: /view plan/i }));
    // A raw <a href> would attempt a document navigation and never render the
    // routed element; a <Link> resolves it in place.
    expect(await screen.findByText('project plan page')).toBeInTheDocument();
  });

  it('fires onPlan and disables while planning=true', async () => {
    const onPlan = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <AssignmentCard
        assignment={buildAssignment()}
        onSubmit={vi.fn()}
        onPlan={onPlan}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        planning={false}
        canPlan={true}
        canManage={false}
      />,
    );
    await user.click(screen.getByRole('button', { name: /plan it out/i }));
    expect(onPlan).toHaveBeenCalledTimes(1);

    rerender(
      <AssignmentCard
        assignment={buildAssignment()}
        onSubmit={vi.fn()}
        onPlan={onPlan}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        planning={true}
        canPlan={true}
        canManage={false}
      />,
    );
    expect(screen.getByRole('button', { name: /planning/i })).toBeDisabled();
  });

  it('shows ↩ Withdraw on a pending submission and fires onWithdraw with the submission id', async () => {
    const onWithdraw = vi.fn();
    const user = userEvent.setup();
    render(
      <AssignmentCard
        assignment={buildAssignment({
          submission_status: { id: 88, status: 'pending' },
        })}
        onSubmit={vi.fn()}
        onPlan={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onWithdraw={onWithdraw}
        planning={false}
        canPlan={false}
        canManage={false}
      />,
    );
    await user.click(screen.getByRole('button', { name: /withdraw/i }));
    expect(onWithdraw).toHaveBeenCalledTimes(1);
    expect(onWithdraw).toHaveBeenCalledWith(88);
  });

  it('does not show Withdraw on an already-approved submission (audit-trail invariant)', () => {
    render(
      <AssignmentCard
        assignment={buildAssignment({
          submission_status: { id: 88, status: 'approved' },
        })}
        onSubmit={vi.fn()}
        onPlan={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onWithdraw={vi.fn()}
        planning={false}
        canPlan={false}
        canManage={false}
      />,
    );
    expect(screen.queryByRole('button', { name: /withdraw/i })).toBeNull();
  });

  it('hides Withdraw when no onWithdraw callback is wired (parent view)', () => {
    render(
      <AssignmentCard
        assignment={buildAssignment({
          submission_status: { id: 88, status: 'pending' },
        })}
        onSubmit={vi.fn()}
        onPlan={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        planning={false}
        canPlan={false}
        canManage={false}
      />,
    );
    expect(screen.queryByRole('button', { name: /withdraw/i })).toBeNull();
  });

  it('gates edit/delete buttons behind canManage and wires both callbacks', async () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <AssignmentCard
        assignment={buildAssignment()}
        onSubmit={vi.fn()}
        onPlan={vi.fn()}
        onEdit={onEdit}
        onDelete={onDelete}
        planning={false}
        canPlan={false}
        canManage={false}
      />,
    );
    expect(screen.queryByRole('button', { name: /edit assignment/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /delete assignment/i })).toBeNull();

    rerender(
      <AssignmentCard
        assignment={buildAssignment()}
        onSubmit={vi.fn()}
        onPlan={vi.fn()}
        onEdit={onEdit}
        onDelete={onDelete}
        planning={false}
        canPlan={false}
        canManage={true}
      />,
    );
    await user.click(screen.getByRole('button', { name: /edit assignment/i }));
    await user.click(screen.getByRole('button', { name: /delete assignment/i }));
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it('parent edit/delete carry the app 44px tap floor (IconButton, not raw ~26px buttons)', () => {
    render(
      <AssignmentCard
        assignment={buildAssignment()}
        onSubmit={vi.fn()}
        onPlan={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        planning={false}
        canPlan={false}
        canManage={true}
      />,
    );
    for (const name of [/edit assignment/i, /delete assignment/i]) {
      const btn = screen.getByRole('button', { name });
      expect(btn.className).toMatch(/min-h-11/);
      expect(btn.className).toMatch(/min-w-11/);
    }
  });
});
