import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AddStepModal from './AddStepModal.jsx';
import { server } from '../../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('AddStepModal', () => {
  it('submits a new step with selected milestone', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(
      http.post(/\/api\/projects\/5\/steps\/$/, () => HttpResponse.json({ id: 1 })),
    );
    render(
      <AddStepModal
        projectId={5}
        milestones={[{ id: 7, title: 'Plan' }]}
        initialMilestoneId={7}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    );
    await user.type(screen.getAllByRole('textbox')[0], 'Cut wood');
    await user.click(screen.getByRole('button', { name: /^add step$/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it('renders the "loose step" option when no milestone selected', () => {
    render(
      <AddStepModal
        projectId={5}
        milestones={[{ id: 7, title: 'Plan' }]}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByText(/no milestone/i)).toBeInTheDocument();
  });
});
