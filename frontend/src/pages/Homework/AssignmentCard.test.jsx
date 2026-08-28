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
        <Route path="/quests/ventures/:id" element={<div>venture plan page</div>} />
      </Routes>,
    );
    await user.click(screen.getByRole('link', { name: /view plan/i }));
    // A raw <a href> would attempt a document navigation and never render the
    // routed element; a <Link> resolves it in place.
    expect(await screen.findByText('venture plan page')).toBeInTheDocument();
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
