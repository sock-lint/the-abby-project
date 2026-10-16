import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SubjectFormModal from './SubjectFormModal.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';
import { selectDropdown } from '../../test/selectDropdown';

describe('SubjectFormModal', () => {
  it.each(['create', 'edit'])('saves a selected icon when users %s a subject', async (mode) => {
    const user = userEvent.setup();
    const item = { id: 5, name: 'Reading', category: 2, icon: '🦉✨', description: 'Find new stories', order: 3 };
    const path = mode === 'edit' ? /\/api\/subjects\/5\/$/ : /\/api\/subjects\/$/;
    const save = spyHandler(mode === 'edit' ? 'patch' : 'post', path, { id: 5 });
    server.use(save.handler);
    render(<SubjectFormModal item={mode === 'edit' ? item : undefined} categories={[{ id: 2, name: 'Learning' }]} onClose={vi.fn()} onSaved={vi.fn()} />);
    if (mode === 'create') {
      await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Reading');
      await selectDropdown(user, screen.getByRole('combobox', { name: 'Category' }), '2');
    }
    await user.click(screen.getByRole('button', { name: 'Choose icon' }));
    await user.click(screen.getByRole('button', { name: 'Book', exact: true }));
    expect(screen.getByRole('textbox', { name: 'Icon', exact: true })).toHaveValue('📖');
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: mode === 'edit' ? 'Update' : 'Create', exact: true }));

    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].url).toMatch(path);
    expect(save.calls[0].method).toBe(mode === 'edit' ? 'PATCH' : 'POST');
    expect(save.calls[0].body).toEqual({
      name: 'Reading', category: 2, icon: '📖',
      description: mode === 'edit' ? 'Find new stories' : '', order: mode === 'edit' ? 3 : 0,
    });
  });

  it('preserves a custom subject icon when editing other fields', async () => {
    const user = userEvent.setup();
    const save = spyHandler('patch', /\/api\/subjects\/5\/$/, { id: 5 });
    server.use(save.handler);
    render(<SubjectFormModal item={{ id: 5, name: 'Reading', category: 2, icon: '🦉✨', description: 'Find new stories', order: 3 }} categories={[{ id: 2, name: 'Learning' }]} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByRole('textbox', { name: 'Icon', exact: true })).toHaveValue('🦉✨');
    await user.type(screen.getByRole('textbox', { name: 'Name' }), ' club');
    await user.click(screen.getByRole('button', { name: 'Update', exact: true }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].url).toMatch(/\/api\/subjects\/5\/$/);
    expect(save.calls[0].body).toEqual({ name: 'Reading club', category: 2, icon: '🦉✨', description: 'Find new stories', order: 3 });
  });

  it('renders new form', () => {
    render(<SubjectFormModal categories={[{ id: 1, name: 'C' }]} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getAllByRole('textbox').length).toBeGreaterThan(0);
  });

  it('edits existing', () => {
    render(
      <SubjectFormModal
        item={{ id: 1, name: 'Math', category: 1 }}
        categories={[{ id: 1, name: 'C' }]}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('Math')).toBeInTheDocument();
  });
});
