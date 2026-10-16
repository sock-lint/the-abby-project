import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CategoryFormModal from './CategoryFormModal.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

describe('CategoryFormModal', () => {
  it.each(['create', 'edit'])('saves a selected icon when users %s a category', async (mode) => {
    const user = userEvent.setup();
    const item = { id: 4, name: 'Art', icon: '🦉✨', color: '#ff0000', description: 'Create something' };
    const path = mode === 'edit' ? /\/api\/categories\/4\/$/ : /\/api\/categories\/$/;
    const save = spyHandler(mode === 'edit' ? 'patch' : 'post', path, { id: 4 });
    server.use(save.handler);
    render(<CategoryFormModal item={mode === 'edit' ? item : undefined} onClose={vi.fn()} onSaved={vi.fn()} />);
    if (mode === 'create') await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Art');

    await user.click(screen.getByRole('button', { name: 'Choose icon' }));
    await user.click(screen.getByRole('button', { name: 'Art', exact: true }));
    expect(screen.getByRole('textbox', { name: 'Icon (emoji)' })).toHaveValue('🎨');
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: mode === 'edit' ? 'Update' : 'Create', exact: true }));

    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].url).toMatch(path);
    expect(save.calls[0].method).toBe(mode === 'edit' ? 'PATCH' : 'POST');
    expect(save.calls[0].body).toEqual({
      name: 'Art', icon: '🎨', color: mode === 'edit' ? '#ff0000' : '#D97706',
      description: mode === 'edit' ? 'Create something' : '',
    });
  });

  it('preserves a custom category icon when editing other fields', async () => {
    const user = userEvent.setup();
    const save = spyHandler('patch', /\/api\/categories\/4\/$/, { id: 4 });
    server.use(save.handler);
    render(<CategoryFormModal item={{ id: 4, name: 'Art', icon: '🦉✨', color: '#ff0000', description: 'Create something' }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByRole('textbox', { name: 'Icon (emoji)' })).toHaveValue('🦉✨');
    await user.type(screen.getByRole('textbox', { name: 'Name' }), ' club');
    await user.click(screen.getByRole('button', { name: 'Update', exact: true }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].url).toMatch(/\/api\/categories\/4\/$/);
    expect(save.calls[0].body).toEqual({ name: 'Art club', icon: '🦉✨', color: '#ff0000', description: 'Create something' });
  });

  it('renders new form', () => {
    render(<CategoryFormModal onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getAllByRole('textbox').length).toBeGreaterThan(0);
  });

  it('edits existing', () => {
    render(
      <CategoryFormModal
        item={{ id: 1, name: 'Art', icon: '🎨', color: '#f00', description: 'x' }}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('Art')).toBeInTheDocument();
  });

  it('submits on save', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(http.post('*/api/categories/', () => HttpResponse.json({ id: 1 })));
    render(<CategoryFormModal onClose={() => {}} onSaved={onSaved} />);
    const inputs = screen.getAllByRole('textbox');
    await user.type(inputs[0], 'Science');
    await user.click(screen.getByRole('button', { name: /create|save/i }));
  });

  it('labels the color picker and shows the existing value', () => {
    render(
      <CategoryFormModal
        item={{ id: 1, name: 'Art', icon: '🎨', color: '#f00', description: 'x' }}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    const color = screen.getByLabelText('Color');
    expect(color).toHaveAttribute('type', 'color');
    expect(color).toHaveValue('#ff0000');
  });

  it('submits a color changed through the labelled picker', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const bodies = [];
    server.use(http.patch(/\/api\/categories\/1\/$/, async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json({ id: 1 });
    }));
    render(
      <CategoryFormModal
        item={{ id: 1, name: 'Art', icon: '🎨', color: '#ff0000', description: 'x' }}
        onClose={() => {}}
        onSaved={onSaved}
      />,
    );
    fireEvent.input(screen.getByLabelText('Color'), { target: { value: '#00ff00' } });
    await user.click(screen.getByRole('button', { name: /update/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(bodies).toHaveLength(1);
    expect(bodies[0]).toMatchObject({ name: 'Art', color: '#00ff00' });
  });
});
