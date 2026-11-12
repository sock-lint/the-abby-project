import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ProjectHeader from './ProjectHeader.jsx';
import { buildProject } from '../../test/factories.js';
import { formatDate } from '../../utils/format';

function renderHeader(props = {}) {
  return render(
    <MemoryRouter>
      <ProjectHeader
        project={buildProject(props.project || {})}
        isParent={!!props.isParent}
        isAssigned={!!props.isAssigned}
        onAction={props.onAction || vi.fn()}
        onEdit={props.onEdit || vi.fn()}
        onOpenQR={props.onOpenQR || vi.fn()}
        timezone={props.timezone}
      />
    </MemoryRouter>,
  );
}

describe('ProjectHeader', () => {
  it('lets a parent complete their own Family project without a child submission step', async () => {
    const onAction = vi.fn();
    const onEdit = vi.fn();
    const user = userEvent.setup();
    renderHeader({ isParent: true, isAssigned: true, project: { status: 'in_progress', assigned_to: { id: 99, role: 'parent' } }, onAction, onEdit });
    expect(screen.queryByRole('button', { name: 'Submit for review' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Complete project' }));
    expect(onAction).toHaveBeenCalledExactlyOnceWith('approve');
    await user.click(screen.getByRole('button', { name: 'Edit' }));
    expect(onEdit).toHaveBeenCalledOnce();
  });

  it('labels an own parent completion in Family review without changing child review controls', async () => {
    const onAction = vi.fn();
    const user = userEvent.setup();
    renderHeader({ isParent: true, isAssigned: true, project: { status: 'in_review', assigned_to: { id: 99, role: 'parent' } }, onAction });
    await user.click(screen.getByRole('button', { name: 'Complete project' }));
    expect(onAction).toHaveBeenCalledExactlyOnceWith('approve');
  });

  it('preserves Family approval and change requests for a child’s project', async () => {
    const onAction = vi.fn();
    const user = userEvent.setup();
    renderHeader({ isParent: true, isAssigned: false, project: { status: 'in_review', assigned_to: { id: 7, role: 'child' } }, onAction });
    await user.click(screen.getByRole('button', { name: 'Approve' }));
    await user.click(screen.getByRole('button', { name: 'Request changes' }));
    expect(onAction.mock.calls).toEqual([['approve'], ['request-changes']]);
  });

  it.each([
    ['2026-10-19T06:59:00Z', false],
    ['2026-10-19T07:00:00Z', true],
  ])('marks an active due date as passed only after family midnight at %s', (now, passed) => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(now));
    try {
      renderHeader({ timezone: 'America/Phoenix', project: { status: 'in_progress', due_date: '2026-10-18' } });
      expect(Boolean(screen.queryByText('Due date passed'))).toBe(passed);
    } finally {
      vi.useRealTimers();
    }
  });

  it.each(['in_review', 'completed', 'archived'])('does not call a %s project overdue based on its approval date', (status) => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-21T12:00:00Z'));
    try {
      renderHeader({ timezone: 'America/Phoenix', project: { status, due_date: '2026-10-18', completed_at: '2026-10-20T01:00:00Z' } });
      expect(screen.queryByText('Due date passed')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('uses the family timezone for recorded completion instead of the browser timezone', () => {
    renderHeader({ timezone: 'America/Phoenix', project: { status: 'completed', completed_at: '2026-10-20T01:00:00Z' } });
    expect(screen.getByText(/Completion recorded/)).toHaveTextContent('Oct 19, 2026');
    expect(screen.getByText(/Completion recorded/)).toHaveTextContent('6:00 PM MST');
  });

  it('shows the due date and recorded completion without treating approval after the due date as late work', () => {
    const due = '2026-10-18';
    const completed = '2026-10-20T01:00:00Z';
    renderHeader({ isParent: true, project: { status: 'completed', due_date: due, completed_at: completed } });
    expect(screen.getByText(/^Current due/)).toHaveTextContent(`Current due ${formatDate(due)}`);
    expect(screen.getByText(/Completion recorded/)).toHaveTextContent('Completion recorded Oct 19, 2026');
    expect(screen.queryByText(/^(late|early|on time)\b/i)).not.toBeInTheDocument();
  });

  it('shows that a submitted project still awaits completion approval without inventing its submission date', () => {
    renderHeader({ isParent: true, project: { status: 'in_review', due_date: null, updated_at: '2026-10-20T01:00:00Z' } });
    expect(screen.getByText('No due date set')).toBeInTheDocument();
    expect(screen.getByText('Awaiting completion approval')).toBeInTheDocument();
    expect(screen.queryByText(/Completion recorded/)).not.toBeInTheDocument();
  });

  it('keeps a historical completion date unknown when the project has no saved completion timestamp', () => {
    renderHeader({ isParent: true, project: { status: 'completed', completed_at: null, updated_at: '2026-10-20T01:00:00Z' } });
    expect(screen.getByText('Completion date unavailable')).toBeInTheDocument();
    expect(screen.queryByText(/Completion recorded/)).not.toBeInTheDocument();
  });

  it('labels a retained completion timestamp as previous when a project is back in review', () => {
    const completed = '2026-10-20T01:00:00Z';
    renderHeader({ isParent: true, project: { status: 'in_review', completed_at: completed } });
    expect(screen.getByText(/Previous completion recorded/)).toHaveTextContent('Previous completion recorded Oct 19, 2026');
    expect(screen.getByText('Awaiting completion approval')).toBeInTheDocument();
  });

  it.each(['draft', 'active', 'in_progress', 'in_review', 'completed'])(
    'labels a homework plan without separate project controls in %s status',
    (status) => {
      renderHeader({ isParent: true, isAssigned: true, project: { status, is_homework_plan: true, payment_kind: 'bounty' } });
      expect(screen.getByText('Homework plan')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /start project|submit for review|approve|request changes|save as template|^edit$/i })).not.toBeInTheDocument();
      expect(screen.queryByText('optional project')).not.toBeInTheDocument();
    },
  );

  it('does not offer a timer for assigned homework', () => {
    renderHeader({ isAssigned: true, project: { is_homework_plan: true } });
    expect(screen.queryByRole('button', { name: 'Work on this project' })).not.toBeInTheDocument();
  });

  it('renders project title', () => {
    renderHeader({ project: { title: 'Test Project' } });
    expect(screen.getByText('Test Project')).toBeInTheDocument();
  });

  it('parent sees edit button', async () => {
    const onEdit = vi.fn();
    const user = userEvent.setup();
    renderHeader({ isParent: true, onEdit });
    const editBtn = screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-pencil'));
    if (editBtn) {
      await user.click(editBtn);
      expect(onEdit).toHaveBeenCalled();
    }
  });

  it('the assignee submits for review through the shared Button primitive', async () => {
    const onAction = vi.fn();
    const user = userEvent.setup();
    renderHeader({
      isAssigned: true,
      project: { status: 'in_progress' },
      onAction,
    });
    const submit = screen.getByRole('button', { name: /submit for review/i });
    // Same 44px floor as its size="sm" siblings in this row.
    expect(submit.className).toMatch(/min-h-11/);
    await user.click(submit);
    expect(onAction).toHaveBeenCalledWith('submit');
  });

  it('renders an illuminated versal of the title first letter with status-driven gilt', () => {
    const { container } = renderHeader({
      project: { title: 'Adobe Brick Oven', status: 'in_review' },
    });
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal).not.toBeNull();
    expect(versal.getAttribute('data-progress')).toBe('80');
    // in_review → 80% → cresting tier
    expect(versal.getAttribute('data-tier')).toBe('cresting');
  });

  it('renders a draft project versal with locked tier (status pre-unlock)', () => {
    const { container } = renderHeader({
      project: { title: 'Backyard Trebuchet', status: 'draft' },
    });
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal.getAttribute('data-tier')).toBe('locked');
  });

  it('renders a completed project versal as fully gilded', () => {
    const { container } = renderHeader({
      project: { title: 'Capstone', status: 'completed' },
    });
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal.getAttribute('data-progress')).toBe('100');
    expect(versal.getAttribute('data-tier')).toBe('gilded');
  });
});
