import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AddMilestoneModal from './AddMilestoneModal.jsx';
import { server } from '../../../test/server.js';
import { spyHandler } from '../../../test/spy.js';
import { useSpace } from '../../../hooks/useSpace';

vi.mock('../../../hooks/useSpace', () => ({ useSpace: vi.fn() }));

beforeEach(() => useSpace.mockReturnValue({ isParentAccount: true, isPersonalSpace: false }));

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('AddMilestoneModal', () => {
  it('adds a parent’s personal milestone without offering or sending a cash bonus', async () => {
    useSpace.mockReturnValue({ isParentAccount: true, isPersonalSpace: true });
    const user = userEvent.setup();
    const create = spyHandler('post', '*/api/projects/5/milestones/', { id: 1 });
    const onSaved = vi.fn();
    server.use(create.handler);
    render(<AddMilestoneModal projectId={5} onClose={vi.fn()} onSaved={onSaved} />);
    expect(screen.queryByRole('spinbutton', { name: 'Bonus ($)' })).not.toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Title' }), 'Cut the pieces');
    await user.click(screen.getByRole('button', { name: /^add milestone$/i }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0]).toMatchObject({ method: 'POST', body: { project: 5, title: 'Cut the pieces', description: '' } });
    expect(create.calls[0].url).toMatch(/\/api\/projects\/5\/milestones\/$/);
    expect(create.calls[0].body).not.toHaveProperty('bonus_amount');
    expect(onSaved).toHaveBeenCalledOnce();
  });

  it('keeps the family milestone bonus in the request', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', '*/api/projects/5/milestones/', { id: 1 });
    server.use(create.handler);
    render(<AddMilestoneModal projectId={5} onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.type(screen.getByRole('textbox', { name: 'Title' }), 'Family milestone');
    await user.type(screen.getByRole('spinbutton', { name: 'Bonus ($)' }), '4.50');
    await user.click(screen.getByRole('button', { name: /^add milestone$/i }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body.bonus_amount).toBe('4.5');
  });

  it('adds a homework phase without offering or sending a cash bonus', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', '*/api/projects/5/milestones/', { id: 1 });
    const onSaved = vi.fn();
    server.use(create.handler);
    render(<AddMilestoneModal projectId={5} isHomeworkPlan onClose={vi.fn()} onSaved={onSaved} />);
    expect(screen.queryByRole('spinbutton', { name: 'Bonus ($)' })).not.toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Title' }), 'Research');
    await user.click(screen.getByRole('button', { name: /^add milestone$/i }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].url).toMatch(/\/api\/projects\/5\/milestones\/$/);
    expect(create.calls[0].body).toEqual({ project: 5, title: 'Research', description: '', bonus_amount: null });
    expect(onSaved).toHaveBeenCalledOnce();
  });

  it('submits a new milestone', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(
      http.post(/\/api\/projects\/5\/milestones\/$/, () => HttpResponse.json({ id: 1 })),
    );
    render(<AddMilestoneModal projectId={5} onClose={vi.fn()} onSaved={onSaved} />);
    await user.type(screen.getAllByRole('textbox')[0], 'Phase 1');
    await user.click(screen.getByRole('button', { name: /^add milestone$/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
