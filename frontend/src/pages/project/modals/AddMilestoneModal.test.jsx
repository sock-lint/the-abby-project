import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AddMilestoneModal from './AddMilestoneModal.jsx';
import { server } from '../../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('AddMilestoneModal', () => {
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
