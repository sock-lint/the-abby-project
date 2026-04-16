import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import EditProjectModal from './EditProjectModal.jsx';
import { server } from '../../../test/server.js';
import { buildProject } from '../../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('EditProjectModal', () => {
  it('submits changes', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(
      http.patch(/\/api\/projects\/1\/$/, () => HttpResponse.json({ id: 1 })),
    );
    render(
      <EditProjectModal project={buildProject({ id: 1, title: 'Old' })} onClose={vi.fn()} onSaved={onSaved} />,
    );
    expect(screen.getByDisplayValue('Old')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
