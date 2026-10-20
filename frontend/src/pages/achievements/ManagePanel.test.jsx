import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ManagePanel from './ManagePanel.jsx';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('ManagePanel', () => {
  it('names duplicate skills by category in management actions and the exact deletion confirmation', async () => {
    const user = userEvent.setup();
    const deletes = vi.fn();
    server.use(
      http.get('*/api/subjects/', () => HttpResponse.json([])),
      http.get('*/api/skills/', () => HttpResponse.json([
        { id: 11, name: 'Improvisation', category: 1, category_name: 'Cooking' },
        { id: 12, name: 'Improvisation', category: 2, category_name: 'Music' },
        { id: 13, name: 'Drawing', category: 3, category_name: 'Art & Crafts' },
      ])),
      http.get('*/api/badges/', () => HttpResponse.json([])),
      http.delete('*/api/skills/:id/', ({ params }) => {
        deletes(params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    render(<ManagePanel categories={[{ id: 1, name: 'Cooking' }, { id: 2, name: 'Music' }, { id: 3, name: 'Art & Crafts' }]} reloadCategories={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /skills/i }));
    expect(await screen.findByRole('button', { name: 'Edit skill Improvisation (Cooking)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete skill Drawing' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete skill Improvisation (Music)' }));
    const confirmation = screen.getByRole('alertdialog', { name: 'Delete Improvisation (Music)?' });
    await user.click(within(confirmation).getByRole('button', { name: 'Delete', exact: true }));
    await waitFor(() => expect(deletes).toHaveBeenCalledExactlyOnceWith('12'));
  });

  it('renders tabs and an initial categories tab', async () => {
    server.use(
      http.get('*/api/subjects/', () => HttpResponse.json([])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      http.get('*/api/badges/', () => HttpResponse.json([])),
    );
    render(<ManagePanel categories={[{ id: 1, name: 'Science', icon: '🔬' }]} reloadCategories={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByRole('button').length).toBeGreaterThan(0));
  });

  it('switches to subjects tab', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/subjects/', () =>
        HttpResponse.json([{ id: 1, name: 'Math', category: 1 }]),
      ),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      http.get('*/api/badges/', () => HttpResponse.json([])),
    );
    render(<ManagePanel categories={[{ id: 1, name: 'C' }]} reloadCategories={vi.fn()} />);
    const subjectsTab = await screen.findByRole('button', { name: /subjects/i });
    await user.click(subjectsTab);
    await waitFor(() => expect(screen.getByText('Math')).toBeInTheDocument());
  });
});
