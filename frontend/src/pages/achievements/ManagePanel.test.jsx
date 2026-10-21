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
  it('keeps a skill and its controls after retirement fails, then permits an explicit retry', async () => {
    const user = userEvent.setup();
    let retired = false;
    const writes = vi.fn();
    server.use(
      http.get('*/api/subjects/', () => HttpResponse.json([])),
      http.get('*/api/skills/', () => HttpResponse.json([{ id: 7, name: 'Saved skill', category: 1, is_retired: retired, available_for_new_choices: !retired }])),
      http.get('*/api/badges/', () => HttpResponse.json([])),
      http.patch('*/api/skills/7/', () => {
        writes();
        if (writes.mock.calls.length === 1) return HttpResponse.json({ detail: 'Retirement is temporarily unavailable.' }, { status: 503 });
        retired = true;
        return HttpResponse.json({ id: 7, is_retired: true, available_for_new_choices: false });
      }),
    );
    render(<ManagePanel categories={[{ id: 1, name: 'Science' }]} reloadCategories={vi.fn()} canManageTaxonomy />);
    await user.click(screen.getByRole('button', { name: /^Skills/ }));
    for (let attempt = 0; attempt < 2; attempt += 1) {
      await user.click(await screen.findByRole('button', { name: 'Retire skill Saved skill' }));
      await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Retire', exact: true }));
      if (attempt === 0) {
        expect(await screen.findByRole('alert')).toHaveTextContent('Retirement is temporarily unavailable.');
        expect(screen.getByRole('button', { name: 'Edit skill Saved skill' })).toBeEnabled();
        expect(writes).toHaveBeenCalledTimes(1);
      }
    }
    await user.click(screen.getByRole('checkbox', { name: 'Show retired taxonomy' }));
    expect(await screen.findByRole('button', { name: 'Restore skill Saved skill' })).toBeInTheDocument();
    expect(writes).toHaveBeenCalledTimes(2);
  });

  it('shows inherited retirement clearly while withholding retirement writes from ordinary parents', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/subjects/', () => HttpResponse.json([])),
      http.get('*/api/skills/', () => HttpResponse.json([{ id: 7, name: 'Inherited skill', category: 1, is_retired: false, available_for_new_choices: false }])),
      http.get('*/api/badges/', () => HttpResponse.json([])),
    );
    render(<ManagePanel categories={[{ id: 1, name: 'Earlier category', is_retired: true, available_for_new_choices: false }]} reloadCategories={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /^Skills/ }));
    await user.click(screen.getByRole('checkbox', { name: 'Show retired taxonomy' }));
    expect(await screen.findByText('Inherited skill')).toBeInTheDocument();
    expect(screen.getByText('Unavailable for new choices (category or subject retired)')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^(Retire|Restore) skill/ })).not.toBeInTheDocument();
  });

  it('retires and restores a saved skill through PATCH while preserving the retirement management view', async () => {
    const user = userEvent.setup();
    let retired = false;
    const updates = [];
    const deleteCall = vi.fn();
    const requests = [];
    server.use(
      http.get('*/api/subjects/', () => HttpResponse.json([])),
      http.get('*/api/skills/', ({ request }) => {
        requests.push(new URL(request.url).searchParams.get('include_retired'));
        return HttpResponse.json([{ id: 7, name: 'Saved skill', category: 1, category_name: 'Science', is_retired: retired, available_for_new_choices: !retired }]);
      }),
      http.get('*/api/badges/', () => HttpResponse.json([])),
      http.patch('*/api/skills/7/', async ({ request }) => {
        const body = await request.json(); updates.push(body); retired = body.is_retired;
        return HttpResponse.json({ id: 7, name: 'Saved skill', is_retired: retired, available_for_new_choices: !retired });
      }),
      http.delete('*/api/skills/7/', () => { deleteCall(); return new HttpResponse(null, { status: 204 }); }),
    );
    render(<ManagePanel categories={[{ id: 1, name: 'Science' }]} reloadCategories={vi.fn()} canManageTaxonomy />);
    await user.click(screen.getByRole('button', { name: /^Skills/ }));
    await user.click(await screen.findByRole('button', { name: 'Retire skill Saved skill' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Retire', exact: true }));
    await waitFor(() => expect(updates).toEqual([{ is_retired: true }]));
    await user.click(screen.getByRole('checkbox', { name: 'Show retired taxonomy' }));
    const restore = await screen.findByRole('button', { name: 'Restore skill Saved skill' });
    expect(screen.getByText('Retired', { exact: true })).toBeInTheDocument();
    await user.click(restore);
    await waitFor(() => expect(updates).toEqual([{ is_retired: true }, { is_retired: false }]));
    expect(await screen.findByRole('button', { name: 'Retire skill Saved skill' })).toBeInTheDocument();
    expect(requests.every((value) => value === 'true')).toBe(true);
    expect(deleteCall).not.toHaveBeenCalled();
  });

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
