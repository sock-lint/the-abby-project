import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import conflict from '../../../contracts/api/fixtures/taxonomy-delete-in-use.json';
import { deleteSkill } from './index';
import ManagePanel from '../pages/achievements/ManagePanel';
import { server } from '../test/server';

describe('protected taxonomy deletion through the React client', () => {
  it('preserves the real server conflict code and readable message', async () => {
    server.use(http.delete('*/api/skills/3/', () => HttpResponse.json(conflict, { status: 409 })));
    await expect(deleteSkill(3)).rejects.toMatchObject({
      status: 409,
      message: conflict.detail,
      response: { code: 'taxonomy_in_use', detail: conflict.detail },
    });
  });

  it.each([
    { type: 'category', tab: 'categories', id: 1, name: 'Science' },
    { type: 'subject', tab: 'subjects', id: 2, name: 'Physics' },
    { type: 'skill', tab: 'skills', id: 3, name: 'Observation' },
  ])('keeps an in-use $type visible and actionable after its exact DELETE is rejected', async ({ type, tab, id, name }) => {
    const user = userEvent.setup();
    const reloadCategories = vi.fn();
    const reads = vi.fn();
    const deletes = vi.fn();
    server.use(
      http.get('*/api/subjects/', () => {
        reads('subjects');
        return HttpResponse.json([{ id: 2, name: 'Physics', category: 1 }]);
      }),
      http.get('*/api/skills/', () => {
        reads('skills');
        return HttpResponse.json([{ id: 3, name: 'Observation', category: 1, category_name: 'Science', subject: 2, subject_name: 'Physics' }]);
      }),
      http.get('*/api/badges/', () => {
        reads('badges');
        return HttpResponse.json([]);
      }),
      http.delete(`*/api/${tab}/${id}/`, ({ request }) => {
        deletes(new URL(request.url).pathname);
        return HttpResponse.json(conflict, { status: 409 });
      }),
    );
    render(<ManagePanel categories={[{ id: 1, name: 'Science' }]} reloadCategories={reloadCategories} />);
    if (tab !== 'categories') await user.click(screen.getByRole('button', { name: new RegExp(`^${tab}`, 'i') }));
    await waitFor(() => expect(reads).toHaveBeenCalledTimes(3));
    await user.click(await screen.findByRole('button', { name: `Delete ${type} ${name}` }));
    const confirmation = screen.getByRole('alertdialog', { name: `Delete ${name}?` });
    await user.click(within(confirmation).getByRole('button', { name: 'Delete', exact: true }));

    expect(await screen.findByRole('alert')).toHaveTextContent(conflict.detail);
    expect(deletes).toHaveBeenCalledExactlyOnceWith(`/api/${tab}/${id}/`);
    expect(screen.getByRole('button', { name: `Delete ${type} ${name}` })).toBeInTheDocument();
    const edit = screen.getByRole('button', { name: `Edit ${type} ${name}` });
    expect(edit).toBeEnabled();
    expect(reads).toHaveBeenCalledTimes(3);
    expect(reloadCategories).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    await user.click(edit);
    expect(screen.getByRole('dialog', { name: `Edit ${type[0].toUpperCase()}${type.slice(1)}` })).toBeInTheDocument();
  });
});
