import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AssignmentCard from './AssignmentCard.jsx';

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
});
