import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AddResourceModal from './AddResourceModal.jsx';
import { server } from '../../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('AddResourceModal', () => {
  it('submits a new resource', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(
      http.post(/\/api\/projects\/5\/resources\/$/, () => HttpResponse.json({ id: 1 })),
    );
    render(
      <AddResourceModal projectId={5} steps={[{ id: 10, title: 'Cut' }]} onClose={vi.fn()} onSaved={onSaved} />,
    );
    await user.type(document.querySelector('input[type="url"]'), 'https://example.com');
    await user.click(screen.getByRole('button', { name: /^add resource$/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
