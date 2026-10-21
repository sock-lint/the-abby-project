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
  it('keeps a retired saved category readable and unchanged on an unrelated project edit', async () => {
    const user = userEvent.setup();
    const updates = [];
    server.use(
      http.get('*/api/categories/', () => HttpResponse.json([
        { id: 7, name: 'Earlier category', is_retired: true, available_for_new_choices: false },
        { id: 8, name: 'Current category', is_retired: false, available_for_new_choices: true },
      ])),
      http.patch('*/api/projects/1/', async ({ request }) => { updates.push(await request.json()); return HttpResponse.json({ id: 1 }); }),
    );
    render(<EditProjectModal project={buildProject({ id: 1, title: 'Old', category: { id: 7, name: 'Earlier category' } })} onClose={vi.fn()} onSaved={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Category' })).toHaveTextContent('Earlier category · Retired'));
    await user.clear(screen.getByLabelText('Title'));
    await user.type(screen.getByLabelText('Title'), 'Updated title');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(updates).toHaveLength(1));
    expect(updates[0]).toMatchObject({ title: 'Updated title', category_id: 7 });
  });

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
