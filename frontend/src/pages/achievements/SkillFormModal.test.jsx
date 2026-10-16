import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SkillFormModal from './SkillFormModal.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

describe('SkillFormModal', () => {
  it.each(['create', 'edit'])('saves a selected icon when users %s a skill', async (mode) => {
    const user = userEvent.setup();
    const item = { id: 6, name: 'Piano', category: 2, subject: 3, icon: '🦉✨', description: 'Practice scales', is_locked_by_default: true, order: 4, level_names: { 0: 'Beginner' } };
    const path = mode === 'edit' ? /\/api\/skills\/6\/$/ : /\/api\/skills\/$/;
    const save = spyHandler(mode === 'edit' ? 'patch' : 'post', path, { id: 6 });
    server.use(save.handler);
    render(<SkillFormModal item={mode === 'edit' ? item : undefined} categories={[{ id: 2, name: 'Art' }]} subjects={[{ id: 3, name: 'Music', category: 2 }]} onClose={vi.fn()} onSaved={vi.fn()} />);
    if (mode === 'create') {
      await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Piano');
      await user.selectOptions(screen.getByRole('combobox', { name: 'Category' }), '2');
      await user.selectOptions(screen.getByRole('combobox', { name: 'Subject', exact: true }), '3');
    }
    await user.click(screen.getByRole('button', { name: 'Choose icon' }));
    await user.click(screen.getByRole('button', { name: 'Music', exact: true }));
    expect(screen.getByRole('textbox', { name: 'Icon', exact: true })).toHaveValue('🎵');
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: mode === 'edit' ? 'Update' : 'Create', exact: true }));

    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].url).toMatch(path);
    expect(save.calls[0].method).toBe(mode === 'edit' ? 'PATCH' : 'POST');
    expect(save.calls[0].body).toEqual({
      name: 'Piano', category: 2, subject: 3, icon: '🎵', description: mode === 'edit' ? 'Practice scales' : '',
      is_locked_by_default: mode === 'edit', order: mode === 'edit' ? 4 : 0,
      level_names: mode === 'edit' ? { 0: 'Beginner' } : {},
    });
  });

  it('preserves a custom skill icon when editing other fields', async () => {
    const user = userEvent.setup();
    const save = spyHandler('patch', /\/api\/skills\/6\/$/, { id: 6 });
    server.use(save.handler);
    render(<SkillFormModal item={{ id: 6, name: 'Piano', category: 2, subject: 3, icon: '🦉✨', description: 'Practice scales', is_locked_by_default: true, order: 4, level_names: { 0: 'Beginner' } }} categories={[{ id: 2, name: 'Art' }]} subjects={[{ id: 3, name: 'Music', category: 2 }]} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByRole('textbox', { name: 'Icon', exact: true })).toHaveValue('🦉✨');
    await user.type(screen.getByRole('textbox', { name: 'Name' }), ' practice');
    await user.click(screen.getByRole('button', { name: 'Update', exact: true }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].url).toMatch(/\/api\/skills\/6\/$/);
    expect(save.calls[0].body).toEqual({ name: 'Piano practice', category: 2, subject: 3, icon: '🦉✨', description: 'Practice scales', is_locked_by_default: true, order: 4, level_names: { 0: 'Beginner' } });
  });

  it('renders new form with category & subject filters', () => {
    render(
      <SkillFormModal
        categories={[{ id: 1, name: 'C' }]}
        subjects={[{ id: 1, name: 'S', category: 1 }, { id: 2, name: 'T', category: 2 }]}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    expect(screen.getAllByRole('textbox').length).toBeGreaterThan(0);
  });

  it('edits existing skill', () => {
    render(
      <SkillFormModal
        item={{ id: 1, name: 'Addition', category: 1, subject: 1, is_locked_by_default: true, order: 3, level_names: {} }}
        categories={[{ id: 1, name: 'C' }]}
        subjects={[{ id: 1, name: 'S', category: 1 }]}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('Addition')).toBeInTheDocument();
  });

  it('toggles is_locked_by_default via its labelled checkbox', async () => {
    const user = userEvent.setup();
    render(
      <SkillFormModal
        categories={[{ id: 1, name: 'C' }]}
        subjects={[]}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    // Now a <CheckboxField>, so the label is associated via htmlFor/id
    // instead of being a hand-rolled wrapper <label>.
    const checkbox = screen.getByLabelText(/locked by default/i);
    expect(checkbox).not.toBeChecked();
    await user.click(checkbox);
    expect(checkbox).toBeChecked();
  });
});
